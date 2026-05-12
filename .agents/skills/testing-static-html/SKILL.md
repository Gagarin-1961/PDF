---
name: testing-static-html
description: Test static HTML landing pages in this repo end-to-end. Use when verifying changes to index.html, visual content, navigation anchors, contact CTAs, or responsive behavior.
---

# Static HTML Testing

## Devin Secrets Needed
- None. This repo currently tests as a public static HTML page with no login, backend, API key, or private data dependency.

## Local setup
1. From the repo root, start a static server:
   ```bash
   python3 -m http.server 8000 --directory /home/ubuntu/repos/PDF
   ```
2. Verify the page is reachable:
   ```bash
   curl -I --max-time 10 http://127.0.0.1:8000/
   ```
3. Validate static HTML syntax:
   ```bash
   python3 - <<'PY'
   from html.parser import HTMLParser
   from pathlib import Path
   class Parser(HTMLParser):
       pass
   Parser().feed(Path('/home/ubuntu/repos/PDF/index.html').read_text(encoding='utf-8'))
   print('HTML parser validation passed')
   PY
   ```
4. If the page includes JSON-LD structured data, parse it with Python `json.loads` before UI testing.

## Browser testing workflow
1. Open `http://127.0.0.1:8000/` in Chrome.
2. Maximize the browser before recording:
   ```bash
   sudo apt-get install -y wmctrl 2>/dev/null; wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz
   ```
3. Record one focused walkthrough that verifies the changed content through the UI.
4. For single-page landing pages, click visible nav anchors instead of using DevTools or console commands.
5. Capture screenshots for key states: hero, changed content section, contact/CTA section, and mobile layout.

## What to assert
- The new brand/title/content is visible and old placeholder strings are absent.
- Anchor navigation scrolls to the expected sections.
- Contact CTAs show the expected `tel:` and `mailto:` values.
- Any representative service/pricing text exactly matches the PR requirements.
- Mobile width hides desktop nav if CSS says it should and keeps the primary logo/CTA/content readable.

## Notes
- This repo currently has no package manager, build command, automated CI workflows, or pre-commit hooks.
- Do not commit generated test reports, screenshots, or recordings to the main feature PR; attach them to the test report/comment instead.
