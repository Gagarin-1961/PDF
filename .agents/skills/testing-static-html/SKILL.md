---
name: testing-static-html
description: Test static HTML landing pages end-to-end in a browser. Use when verifying changes to index.html or other frontend-only static pages in this repo.
---

# Static HTML Browser Testing

## Devin Secrets Needed

- None for local static HTML testing in this repo.

## When to Use

Use this skill when a change adds or modifies static HTML/CSS content and the goal is to verify user-visible layout, navigation anchors, CTAs, and responsive behavior.

## Setup

1. From the repo root, start a local static server:
   ```bash
   python3 -m http.server 8000 --directory .
   ```
2. Verify the page is reachable:
   ```bash
   python3 - <<'PY'
   from urllib.request import urlopen
   html = urlopen('http://localhost:8000/', timeout=5).read().decode('utf-8')
   print('Lumière Beauty Salon' in html or '<!DOCTYPE html>' in html)
   PY
   ```
3. For GUI recording, maximize Chrome before starting the recording:
   ```bash
   wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz
   ```

## Recommended Test Flow

1. Open `http://localhost:8000/` in Chrome.
2. Verify the browser title, hero headline, visible navigation, primary CTA, and key visual styling.
3. Click each same-page navigation/CTA path that should scroll to content, such as services, gallery, and booking sections.
4. Verify exact section headings, expected card titles/prices, visible images, opening hours, and CTA labels.
5. Verify non-visual link targets from source or DOM when clicking would launch an external app, e.g. `mailto:` appointment buttons.
6. Resize Chrome to mobile width with `wmctrl -r :ACTIVE: -b remove,maximized_vert,maximized_horz; wmctrl -r :ACTIVE: -e 0,0,0,430,760` and verify desktop nav collapses/hides as expected, key CTA remains visible, and cards stack without horizontal scrolling.

## Useful Checks

Static HTML sanity check:
```bash
python3 - <<'PY'
from html.parser import HTMLParser
from pathlib import Path
class Parser(HTMLParser):
    pass
Parser().feed(Path('index.html').read_text())
print('HTML parser check passed')
PY
```

Extract a CTA href without opening external applications:
```bash
python3 - <<'PY'
from html.parser import HTMLParser
from pathlib import Path
class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_a = False; self.href = None; self.text = ''
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.in_a = True; self.href = dict(attrs).get('href'); self.text = ''
    def handle_data(self, data):
        if self.in_a:
            self.text += data
    def handle_endtag(self, tag):
        if tag == 'a' and self.in_a:
            if 'Request Appointment' in self.text:
                print(self.href)
            self.in_a = False
parser = Links(); parser.feed(Path('index.html').read_text())
PY
```

## Reporting

- Attach the recording if browser interactions were tested.
- Include screenshots for desktop hero, key sections, and mobile layout.
- If there is no CI or deployment preview, state that local static server testing was used instead.
