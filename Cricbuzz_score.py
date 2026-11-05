"""
cricbuzz_score.py
Week 1 - Day 3 - Task 1: Capture a live cricket score with Playwright (sync API)

What it does
  1. Opens cricbuzz.com in a real browser (headed by default).
  2. WAITS for a live-score element to become visible (no fixed sleep).
  3. Prints the score + match status to the terminal.
  4. Saves a screenshot as score.png.
  5. If no match is live, it says so (and still saves a screenshot) instead of crashing.

Usage
  python cricbuzz_score.py                 # headed - watch it work
  python cricbuzz_score.py --headless      # headless - confirm it still works
  python cricbuzz_score.py --inspect       # list the elements that look like a score,
                                           # with tag + class, so YOU can pick the selector

Setup
  pip install playwright
  playwright install chromium
"""

import argparse
import re
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

# ----------------------------- Configuration ------------------------------
URLS = [
    "https://www.cricbuzz.com/",                          # as given in the assignment
    "https://www.cricbuzz.com/cricket-match/live-scores",  # fallback if the home page has no score
]

# Step 2 of the assignment: find the score element yourself.
# Run `python cricbuzz_score.py --inspect`, check the printed tag/class in the
# browser console with document.querySelector("..."), then paste it here.
#   e.g. SCORE_SELECTOR = "div.some-class"
# While this is None the script finds the score by its text pattern (e.g. 287/4 (45.2)).
SCORE_SELECTOR = None

WAIT_MS = 20_000          # max time to WAIT (returns the moment the element appears)
SCREENSHOT = "score.png"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 287/4 (45.2)  |  287-4 (45.2 Ov)  |  120/2 (20 overs)
SCORE_RE = re.compile(r"\d{1,3}\s*[-/]\s*\d{1,2}\s*\(\s*\d{1,3}(?:\.\d)?\s*(?:ov|overs?)?\s*\)", re.I)
STATUS_RE = re.compile(
    r"\b(need|needs|won|lead|leads|trail|trails|opt|elected|stumps|innings break|"
    r"rain|delayed|abandoned|tied|no result|day \d|toss|starts|target)\b",
    re.I,
)


# --------------------------- Text -> output format -------------------------
def _tidy_score(line):
    """Make '287-4 (45.2)' look like '287/4 (45.2 Ov)'."""
    def fix(m):
        s = re.sub(r"\s+", " ", m.group(0))
        s = re.sub(r"\s*-\s*", "/", s, count=1)
        s = re.sub(r"\(\s*(\d{1,3}(?:\.\d)?)\s*(?:ov|overs?)?\s*\)", r"(\1 Ov)", s, flags=re.I)
        return s
    return SCORE_RE.sub(fix, line)


def parse_card(text):
    """Turn the text of a match card into (score_line, match_line).
    Either can be None if it is not found."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]

    score_line = None
    for i, line in enumerate(lines):
        m = SCORE_RE.search(line)
        if not m:
            continue
        prefix = line[:m.start()].strip()
        # score on its own line -> take the team name from the line above it
        if not re.search(r"[A-Za-z]", prefix) and i > 0 and len(lines[i - 1]) <= 25 \
                and not SCORE_RE.search(lines[i - 1]):
            line = f"{lines[i - 1]} {line}"
        score_line = _tidy_score(line)
        break

    title = next((l.split(",")[0].strip() for l in lines if " vs " in l.lower()), None)
    status = next((l for l in lines if STATUS_RE.search(l) and not SCORE_RE.search(l)
                   and l.lower() != (title or "").lower()), None)

    if title and status:
        match_line = f"{title} - {status}"
    else:
        match_line = title or status
    return score_line, match_line


# ------------------------------ Playwright part ----------------------------
def locate_score(page):
    """Return a locator for the score element, WAITING until it is visible.
    Returns None if nothing shows up within WAIT_MS (e.g. no match live)."""
    if SCORE_SELECTOR:
        locator = page.locator(SCORE_SELECTOR).first
    else:
        locator = page.get_by_text(SCORE_RE).first
    try:
        locator.wait_for(state="visible", timeout=WAIT_MS)   # event-based wait, no sleep()
        return locator
    except PlaywrightTimeout:
        return None


def card_text(score_el):
    """Text of the match card around the score (the nearest enclosing link),
    falling back to the score's grandparent."""
    card = score_el.locator("xpath=ancestor::a[1]")
    if card.count():
        return card.inner_text()
    return score_el.locator("xpath=../..").inner_text()


def inspect_page(page):
    """Print every smallest element whose text looks like a score, with its
    tag/class chain - use this to choose SCORE_SELECTOR yourself."""
    try:
        page.wait_for_load_state("networkidle", timeout=WAIT_MS)
    except PlaywrightTimeout:
        pass
    found = page.evaluate(
        """(pattern) => {
            const re = new RegExp(pattern, "i");
            const out = [];
            for (const el of document.querySelectorAll("body *")) {
                const txt = (el.innerText || "").trim();
                if (!txt || txt.length > 200 || !re.test(txt)) continue;
                if ([...el.children].some(c => re.test(c.innerText || ""))) continue;
                const chain = [];
                let n = el;
                for (let i = 0; i < 4 && n; i++, n = n.parentElement) {
                    const cls = (typeof n.className === "string" && n.className.trim())
                        ? "." + n.className.trim().split(/\\s+/).join(".") : "";
                    chain.push(n.tagName.toLowerCase() + cls);
                }
                out.push({ text: txt.replace(/\\s+/g, " "), chain });
            }
            return out.slice(0, 10);
        }""",
        SCORE_RE.pattern,
    )
    if not found:
        print("No score-like elements on this page right now (is a match live?).")
        return
    for i, item in enumerate(found, 1):
        print(f"\n#{i}  text : {item['text']}")
        print(f"    chain: {'  <  '.join(item['chain'])}")
    print("\nTry one of these in the browser console, e.g.  document.querySelector(\"tag.class\")")


def run(headless, inspect):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="en-IN",
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        try:
            score_el = None
            for url in URLS:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                if inspect:
                    inspect_page(page)
                    return 0
                score_el = locate_score(page)
                if score_el:
                    break

            if score_el is None:
                print("No live match found right now - no score appeared on Cricbuzz.")
                page.screenshot(path=SCREENSHOT)
                print(f"saved {SCREENSHOT}")
                return 0

            score_line, match_line = parse_card(card_text(score_el))
            if score_line is None:                       # custom selector: just print its text
                score_line = score_el.inner_text().strip()

            print(score_line)
            if match_line:
                print(match_line)

            score_el.scroll_into_view_if_needed()
            score_el.evaluate("e => { e.style.outline = '3px solid #e11'; }")  # highlight it
            page.screenshot(path=SCREENSHOT)
            print()
            print(f"saved {SCREENSHOT}")
            return 0
        finally:
            browser.close()


def main():
    ap = argparse.ArgumentParser(description="Capture a live Cricbuzz score with Playwright.")
    ap.add_argument("--headless", action="store_true", help="run without a visible browser window")
    ap.add_argument("--inspect", action="store_true", help="list score-like elements and their classes")
    args = ap.parse_args()
    try:
        sys.exit(run(headless=args.headless, inspect=args.inspect))
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()