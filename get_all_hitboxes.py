#!/usr/bin/env python3
"""
Fetch hitbox image URLs for every SF6 character on supercombo.gg.

Pulls the live character roster from the SF6 hub page, then for each
character scrapes all move sections (Normals → Super Arts) and collects
hitbox image URLs.

Usage:
    python get_all_hitboxes.py                  # print all hitbox URLs
    python get_all_hitboxes.py --download        # download all images
    python get_all_hitboxes.py --output-dir DIR  # set download folder (default: ./hitboxes)
    python get_all_hitboxes.py --no-hitbox       # non-hitbox images instead
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

WIKI_BASE = "https://wiki.supercombo.gg"
API_URL   = WIKI_BASE + "/api.php"
HUB_PAGE  = "Street_Fighter_6"

MOVE_SECTION_IDS = {
    "Normals", "Command_Normals", "Target_Combos",
    "Throws", "Drive_System", "Special_Moves", "Super_Arts",
}

# ── shared helpers ────────────────────────────────────────────────────────────

def fetch_parsed_html(page_title: str) -> str:
    params = (
        "?action=parse"
        f"&page={urllib.parse.quote(page_title, safe='/')}"
        "&prop=text&format=json"
    )
    req = urllib.request.Request(
        API_URL + params,
        headers={"User-Agent": "Mozilla/5.0 (compatible; WikiScraper/1.0)"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["parse"]["text"]["*"]


def list_sections(html: str) -> list:
    return [
        (i, m.group(1))
        for i, m in enumerate(re.finditer(r'<h2[^>]+\bid=["\']([^"\']+)["\']', html))
    ]


def get_section_html(html: str, section_num: int) -> str:
    positions = [m.start() for m in re.finditer(r"<h2[^>]+\bid=", html)]
    if section_num >= len(positions):
        raise ValueError(f"Section {section_num} not found.")
    start = positions[section_num]
    end   = positions[section_num + 1] if section_num + 1 < len(positions) else len(html)
    return html[start:end]


def full_image_url(src: str) -> str:
    src = re.sub(r"/images/thumb/", "/images/", src)
    src = re.sub(r"/[^/]+$", "", src)
    return src


def extract_image_urls(section_html: str, filter_name: str = "") -> list:
    urls = []
    for img_tag in re.findall(r"<img\b[^>]+>", section_html):
        m = re.search(r'\bsrc=["\']([^"\']+)["\']', img_tag)
        if not m:
            continue
        src = m.group(1)
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = WIKI_BASE + src
        src = full_image_url(src)
        if filter_name and filter_name.lower() not in src.lower():
            continue
        urls.append(src)
    return urls

# ── character roster ──────────────────────────────────────────────────────────

def get_sf6_characters(html: str) -> list:
    pattern = re.compile(
        r'class="sc-char-icon"[^>]*>.*?'
        r'<a\s+href="(/w/(Street_Fighter_6/[^"]+))"'
        r'\s+title="Street Fighter 6/([^"]+)"',
        re.DOTALL,
    )
    characters = []
    seen = set()
    for m in pattern.finditer(html):
        page_path = m.group(2)
        disp_name = m.group(3)
        if page_path in seen:
            continue
        seen.add(page_path)
        characters.append({"name": disp_name, "title": page_path})
    return characters

# ── per-character image collection ───────────────────────────────────────────

def get_character_hitbox_urls(page_title: str, hitbox_mode: str) -> list:
    """Return all hitbox (or non-hitbox) move image URLs for one character."""
    filter_name = page_title.split("/")[-1]
    try:
        html = fetch_parsed_html(page_title)
    except Exception as exc:
        print(f"  WARNING: could not fetch {page_title}: {exc}", file=sys.stderr)
        return []

    sections = list_sections(html)
    section_ids = {sid: num for num, sid in sections}
    move_nums = sorted(
        num for sid, num in section_ids.items() if sid in MOVE_SECTION_IDS
    )

    seen = set()
    urls = []
    for snum in move_nums:
        try:
            section_html = get_section_html(html, snum)
        except ValueError:
            continue
        for u in extract_image_urls(section_html, filter_name):
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if hitbox_mode == "hitbox":
        urls = [u for u in urls if "hitbox" in u.lower()]
    elif hitbox_mode == "no-hitbox":
        urls = [u for u in urls if "hitbox" not in u.lower()]

    return urls

# ── download ──────────────────────────────────────────────────────────────────

def download_images(urls: list, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    total = len(urls)
    for i, url in enumerate(urls, 1):
        filename = urllib.parse.unquote(url.split("/")[-1])
        dest = os.path.join(output_dir, filename)
        if os.path.exists(dest):
            print(f"  [{i}/{total}] skip (exists): {filename}")
            continue
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WikiScraper/1.0)"},
            )
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            print(f"  [{i}/{total}] saved: {filename}")
        except Exception as exc:
            print(f"  [{i}/{total}] ERROR {filename}: {exc}", file=sys.stderr)

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    download    = "--download" in sys.argv
    hitbox_mode = "no-hitbox" if "--no-hitbox" in sys.argv else "hitbox"
    output_dir  = "./hitboxes"

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--output-dir" and i < len(sys.argv) - 1:
            output_dir = sys.argv[i + 1]
        elif arg.startswith("--output-dir="):
            output_dir = arg.split("=", 1)[1]

    print(f"Fetching SF6 character roster from hub page…")
    hub_html    = fetch_parsed_html(HUB_PAGE)
    characters  = get_sf6_characters(hub_html)
    print(f"Found {len(characters)} characters.\n")

    all_urls = []
    for i, char in enumerate(characters):
        if i > 0:
            time.sleep(0.5)  # be polite to the wiki server
        print(f"[{char['name']}] scraping {hitbox_mode} images…", end=" ", flush=True)
        urls = get_character_hitbox_urls(char["title"], hitbox_mode)
        print(f"{len(urls)} found")
        all_urls.extend(urls)

        if download and urls:
            char_dir = os.path.join(output_dir, char["name"])
            print(f"  → downloading to {char_dir}/")
            download_images(urls, char_dir)

    print(f"\nTotal: {len(all_urls)} {hitbox_mode} image(s) across {len(characters)} characters.")
    if download:
        print(f"Saved under {output_dir}/<character name>/")
    else:
        print()
        for url in all_urls:
            print(url)


if __name__ == "__main__":
    main()
