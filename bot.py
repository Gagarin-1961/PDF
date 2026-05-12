"""
Telegram-бот для общения с моделью Qwen (DashScope API).

Использует aiogram 3.x для работы с Telegram Bot API
и httpx для асинхронных HTTP-запросов к OpenAI-совместимому эндпоинту Qwen.
"""

import asyncio
import logging
import os
import sys
from collections import defaultdict
from typing import Any

import httpx
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
QWEN_TOKEN: str = os.getenv("QWEN_TOKEN", "")
DEFAULT_MODEL: str = os.getenv("QWEN_MODEL", "qwen-plus")

QWEN_API_URL = (
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
)

TELEGRAM_MSG_LIMIT = 4096

AVAILABLE_MODELS = {"qwen-turbo", "qwen-plus", "qwen-max"}

# ---------------------------------------------------------------------------
# Per-user state (in-memory, no DB)
# ---------------------------------------------------------------------------
user_histories: dict[int, list[dict[str, str]]] = defaultdict(list)
user_models: dict[int, str] = {}

# ---------------------------------------------------------------------------
# HTTP client (shared across requests; created/closed with bot lifecycle)
# ---------------------------------------------------------------------------
http_client: httpx.AsyncClient | None = None

# ---------------------------------------------------------------------------
# Router & handlers
# ---------------------------------------------------------------------------
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start."""
    await message.answer(
        "👋 Привет! Я бот, подключённый к модели <b>Qwen</b>.\n\n"
        "Просто отправь мне текстовое сообщение — и я передам его в Qwen API, "
        "а затем верну ответ.\n\n"
        "<b>Команды:</b>\n"
        "/new — сбросить историю диалога\n"
        "/model &lt;название&gt; — сменить модель "
        f"({', '.join(sorted(AVAILABLE_MODELS))})\n\n"
        f"Текущая модель: <b>{_get_model(message.from_user.id)}</b>",
        parse_mode=ParseMode.HTML,
    )
    logger.info("User %s started the bot", message.from_user.id)


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    """Сброс истории диалога."""
    uid = message.from_user.id
    user_histories[uid].clear()
    await message.answer("🗑 История диалога очищена. Начнём сначала!")
    logger.info("User %s reset conversation history", uid)


@router.message(Command("model"))
async def cmd_model(message: Message) -> None:
    """Смена модели Qwen."""
    uid = message.from_user.id
    parts = message.text.strip().split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Укажите название модели после команды.\n"
            f"Доступные модели: {', '.join(sorted(AVAILABLE_MODELS))}\n"
            f"Текущая модель: <b>{_get_model(uid)}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    model_name = parts[1].strip().lower()
    if model_name not in AVAILABLE_MODELS:
        await message.answer(
            f"⚠️ Неизвестная модель: <b>{model_name}</b>\n"
            f"Доступные: {', '.join(sorted(AVAILABLE_MODELS))}",
            parse_mode=ParseMode.HTML,
        )
        return

    user_models[uid] = model_name
    user_histories[uid].clear()
    await message.answer(
        f"✅ Модель изменена на <b>{model_name}</b>. История диалога сброшена.",
        parse_mode=ParseMode.HTML,
    )
    logger.info("User %s switched model to %s", uid, model_name)


@router.message(F.text)
async def handle_text(message: Message, bot: Bot) -> None:
    """Обработка произвольного текста — отправка в Qwen API."""
    uid = message.from_user.id
    user_text = message.text.strip()

    if not user_text:
        return

    model = _get_model(uid)
    user_histories[uid].append({"role": "user", "content": user_text})

    # Индикатор «печатает…»
    typing_task = asyncio.create_task(_keep_typing(bot, message.chat.id))

    try:
        reply = await _call_qwen(uid, model)
    except QwenApiError as exc:
        typing_task.cancel()
        await message.answer(f"⚠️ Ошибка API: {exc}")
        # Убираем последнее сообщение пользователя, чтобы не ломать контекст
        if user_histories[uid]:
            user_histories[uid].pop()
        return
    finally:
        typing_task.cancel()

    user_histories[uid].append({"role": "assistant", "content": reply})

    # Разбиваем длинный ответ на части по 4096 символов
    for chunk in _split_text(reply, TELEGRAM_MSG_LIMIT):
        await message.answer(chunk)


# ---------------------------------------------------------------------------
# Qwen API helpers
# ---------------------------------------------------------------------------
class QwenApiError(Exception):
    """Обёртка для ошибок при обращении к Qwen API."""


def _get_model(uid: int) -> str:
    return user_models.get(uid, DEFAULT_MODEL)


async def _call_qwen(uid: int, model: str) -> str:
    """Отправляет историю сообщений в Qwen API и возвращает ответ."""
    assert http_client is not None, "HTTP client not initialized"

    payload: dict[str, Any] = {
        "model": model,
        "messages": user_histories[uid],
    }
    headers = {
        "Authorization": f"Bearer {QWEN_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = await http_client.post(
            QWEN_API_URL,
            json=payload,
            headers=headers,
            timeout=120.0,
        )
    except httpx.TimeoutException:
        logger.error("Qwen API timeout for user %s", uid)
        raise QwenApiError(
            "Превышено время ожидания ответа от Qwen. Попробуйте позже."
        )
    except httpx.HTTPError as exc:
        logger.error("HTTP error for user %s: %s", uid, exc)
        raise QwenApiError(f"Ошибка соединения с Qwen API: {exc}")

    if response.status_code == 401:
        logger.error("Invalid QWEN_TOKEN (401)")
        raise QwenApiError("Неверный API-ключ Qwen. Обратитесь к администратору.")

    if response.status_code == 429:
        logger.warning("Rate limit hit for user %s", uid)
        raise QwenApiError(
            "Превышен лимит запросов к Qwen API. Подождите немного и попробуйте снова."
        )

    if response.status_code != 200:
        body = response.text[:300]
        logger.error(
            "Qwen API error %s for user %s: %s", response.status_code, uid, body
        )
        raise QwenApiError(
            f"Qwen API вернул код {response.status_code}. Попробуйте позже."
        )

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Unexpected Qwen response structure: %s — %s", exc, data)
        raise QwenApiError("Не удалось разобрать ответ от Qwen API.")


async def _keep_typing(bot: Bot, chat_id: int) -> None:
    """Периодически отправляет sendChatAction(typing) пока задача не отменена."""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


def _split_text(text: str, limit: int) -> list[str]:
    """Разбивает текст на части не длиннее limit символов."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Ищем последний перенос строки в пределах лимита
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            # Если нет переноса — режем по пробелу
            split_pos = text.rfind(" ", 0, limit)
        if split_pos == -1:
            # Если нет пробела — режем жёстко
            split_pos = limit
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    global http_client

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is not set!")
        sys.exit(1)
    if not QWEN_TOKEN:
        logger.critical("QWEN_TOKEN is not set!")
        sys.exit(1)

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    http_client = httpx.AsyncClient()
    logger.info("Bot started. Default model: %s", DEFAULT_MODEL)

    try:
        await dp.start_polling(bot)
    finally:
        await http_client.aclose()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
