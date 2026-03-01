#!/usr/bin/env python3
"""
Fetch the current list of Street Fighter 6 character page titles from
the supercombo.gg wiki's SF6 hub page.

Parses <a href="/w/Street_Fighter_6/..."> links inside .sc-char-icon spans,
which is where the character roster grid lives.

Usage:
    python get_sf6_characters.py              # print names, one per line
    python get_sf6_characters.py --urls       # print full wiki URLs
    python get_sf6_characters.py --titles     # print API page titles (e.g. Street_Fighter_6/Ryu)
"""

import json
import re
import sys
import urllib.request

HUB_PAGE  = "Street_Fighter_6"
API_URL   = "https://wiki.supercombo.gg/api.php"
BASE_URL  = "https://wiki.supercombo.gg"


def fetch_parsed_html(page_title: str) -> str:
    url = (
        f"{API_URL}?action=parse&page={urllib.parse.quote(page_title)}"
        f"&prop=text&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return data["parse"]["text"]["*"]


# urllib.parse imported lazily above — make sure it's available
import urllib.parse


def get_sf6_characters(html: str) -> list[dict]:
    """
    Return a list of dicts with keys:
        name   – display name  (e.g. "Dee Jay")
        title  – wiki page title with underscores  (e.g. "Street_Fighter_6/Dee_Jay")
        url    – full URL  (e.g. "https://wiki.supercombo.gg/w/Street_Fighter_6/Dee_Jay")
    """
    # Match anchor tags inside sc-char-icon spans.
    # Pattern: <a href="/w/Street_Fighter_6/..." title="Street Fighter 6/NAME">
    pattern = re.compile(
        r'class="sc-char-icon"[^>]*>.*?'      # open sc-char-icon span
        r'<a\s+href="(/w/(Street_Fighter_6/[^"]+))"'  # capture href and path
        r'\s+title="Street Fighter 6/([^"]+)"',       # capture display name
        re.DOTALL,
    )

    characters = []
    seen = set()
    for m in pattern.finditer(html):
        href_path  = m.group(1)   # e.g. /w/Street_Fighter_6/Dee_Jay
        page_path  = m.group(2)   # e.g. Street_Fighter_6/Dee_Jay
        disp_name  = m.group(3)   # e.g. Dee Jay

        if page_path in seen:
            continue
        seen.add(page_path)

        characters.append({
            "name":  disp_name,
            "title": page_path,
            "url":   BASE_URL + href_path,
        })

    return characters


def main():
    mode = "--names"
    for arg in sys.argv[1:]:
        if arg in ("--urls", "--titles", "--names"):
            mode = arg

    html = fetch_parsed_html(HUB_PAGE)
    characters = get_sf6_characters(html)

    if not characters:
        print("No characters found — the page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    for c in characters:
        if mode == "--urls":
            print(c["url"])
        elif mode == "--titles":
            print(c["title"])
        else:
            print(c["name"])


if __name__ == "__main__":
    main()
