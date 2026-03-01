#!/usr/bin/env python3
"""
Extract image URLs from citizen-section-N on a supercombo.gg wiki page.

Uses the MediaWiki API to fetch parsed HTML (bypasses bot-protection on the
regular page URL), then locates the requested section by counting <h2> tags
the same way the Citizen skin does at runtime:
  citizen-section-0  = TOC heading
  citizen-section-1  = first real h2 (e.g. Introduction)
  citizen-section-2  = second h2 (e.g. Normals)
  ...

Usage:
    python get_wiki_images.py [page_title] [section_number] [filter_name] [hitbox_mode]

Examples:
    python get_wiki_images.py "Street_Fighter_6/Ryu"                      # section 1, auto-filter
    python get_wiki_images.py "Street_Fighter_6/Ryu" 2                    # Normals only
    python get_wiki_images.py "Street_Fighter_6/Ryu" all                  # Normals → Super Arts
    python get_wiki_images.py "Street_Fighter_6/Ryu" all Ryu hitbox       # hitbox images only
    python get_wiki_images.py "Street_Fighter_6/Ryu" all Ryu no-hitbox    # non-hitbox images only
    python get_wiki_images.py "Street_Fighter_6/Ken" all                  # all Ken move images

Defaults:
    page_title   = Street_Fighter_6/Ryu
    section_num  = 1
    filter_name  = last segment of page_title (e.g. "Ryu")
    hitbox_mode  = "" (all images; use "hitbox" or "no-hitbox" to filter)

Flags:
    --download          Download all matched images to a local folder
    --output-dir DIR    Folder to save images into (default: ./downloaded_images)
"""

import sys
import re
import json
import os
import urllib.request
import urllib.parse

WIKI_BASE = "https://wiki.supercombo.gg"
API_URL   = WIKI_BASE + "/api.php"


def fetch_parsed_html(page_title: str) -> str:
    """Fetch the parsed HTML body of a wiki page via the MediaWiki API."""
    params = (
        "?action=parse"
        f"&page={urllib.parse.quote(page_title, safe='/')}"
        "&prop=text"
        "&format=json"
    )
    req = urllib.request.Request(
        API_URL + params,
        headers={"User-Agent": "Mozilla/5.0 (compatible; WikiImageScraper/1.0)"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["parse"]["text"]["*"]


def list_sections(html: str) -> list:
    """Return [(section_num, section_id), ...] for all h2 elements."""
    return [
        (i, m.group(1))
        for i, m in enumerate(re.finditer(r'<h2[^>]+\bid=["\']([^"\']+)["\']', html))
    ]


def get_section_html(html: str, section_num: int) -> str:
    """Return the HTML slice for citizen-section-{section_num}."""
    positions = [m.start() for m in re.finditer(r"<h2[^>]+\bid=", html)]
    if section_num >= len(positions):
        raise ValueError(
            f"Section {section_num} not found. "
            f"Valid range: 0–{len(positions) - 1}."
        )
    start = positions[section_num]
    end   = positions[section_num + 1] if section_num + 1 < len(positions) else len(html)
    return html[start:end]


def full_image_url(src: str) -> str:
    """
    Convert a MediaWiki thumbnail URL to the full-resolution image URL.

    Thumbnail pattern:
        /images/thumb/<a>/<ab>/Filename.ext/NNNpx-Filename.ext
    Full image pattern:
        /images/<a>/<ab>/Filename.ext
    """
    # Remove /thumb/ and the trailing /NNNpx-Filename.ext size suffix
    src = re.sub(r"/images/thumb/", "/images/", src)
    src = re.sub(r"/[^/]+$", "", src)  # strip the last path segment (size prefix)
    return src


def extract_image_urls(section_html: str, filter_name: str = "") -> list:
    """Return absolute full-resolution image URLs from all <img> tags in the HTML slice.

    If filter_name is given, only URLs whose filename contains that string
    (case-insensitive) are returned.
    """
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


def download_images(urls: list, output_dir: str) -> None:
    """Download a list of image URLs into output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    total = len(urls)
    for i, url in enumerate(urls, 1):
        filename = url.split("/")[-1]
        dest = os.path.join(output_dir, filename)
        print(f"[{i}/{total}] {filename} ... ", end="", flush=True)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WikiImageScraper/1.0)"},
            )
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            print(f"OK ({len(data):,} bytes)")
        except Exception as exc:
            print(f"FAILED ({exc})")
    print(f"\nDone. Files saved to: {os.path.abspath(output_dir)}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    do_download = "--download" in flags
    output_dir  = "downloaded_images"
    for flag in flags:
        if flag.startswith("--output-dir="):
            output_dir = flag.split("=", 1)[1]
        elif flag == "--output-dir":
            # handled positionally if someone passes it as two tokens
            idx = sys.argv.index("--output-dir")
            if idx + 1 < len(sys.argv):
                output_dir = sys.argv[idx + 1]

    page_title   = args[0] if len(args) > 0 else "Street_Fighter_6/Ryu"
    raw_section  = args[1] if len(args) > 1 else "1"
    # "all" = Normals through Super Arts; otherwise an integer section number
    section_num  = -1 if raw_section.lower() == "all" else int(raw_section)
    # Default filter: last segment of the page title (e.g. "Ryu" from "Street_Fighter_6/Ryu")
    # Pass a third argument to override, or "" to disable filtering.
    default_filter = page_title.split("/")[-1]
    filter_name    = args[2] if len(args) > 2 else default_filter
    # Optional 4th argument: "hitbox", "no-hitbox", or "" (default = all)
    hitbox_mode    = args[3].lower() if len(args) > 3 else ""

    print(f"Page   : {page_title}")
    print(f"Section: {'all move sections (Normals→Super Arts)' if section_num == -1 else f'citizen-section-{section_num}'}")
    print(f"Filter : {filter_name!r} (only URLs containing this name)")
    if hitbox_mode:
        print(f"Hitbox : {hitbox_mode}")
    print()

    try:
        html = fetch_parsed_html(page_title)
    except Exception as exc:
        print(f"ERROR fetching page: {exc}")
        sys.exit(1)

    sections = list_sections(html)

    # Determine which sections to scrape.
    # "all-moves" spans Normals → Super Arts by finding those h2 ids.
    MOVE_SECTION_IDS = {
        "Normals", "Command_Normals", "Target_Combos",
        "Throws", "Drive_System", "Special_Moves", "Super_Arts",
    }
    section_ids = {sid: num for num, sid in sections}
    move_section_nums = sorted(
        num for sid, num in section_ids.items() if sid in MOVE_SECTION_IDS
    )

    print("Available sections:")
    for num, sid in sections:
        if section_num == -1:
            marker = "  <-- included" if sid in MOVE_SECTION_IDS else ""
        else:
            marker = "  <-- requested" if num == section_num else ""
        print(f"  citizen-section-{num}  ({sid}){marker}")
    print()

    if section_num == -1:
        # Special sentinel: pull all move sections
        target_sections = move_section_nums
    else:
        target_sections = [section_num]

    seen = set()
    urls = []
    for snum in target_sections:
        try:
            section_html = get_section_html(html, snum)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        for u in extract_image_urls(section_html, filter_name):
            if u not in seen:
                seen.add(u)
                urls.append(u)

    if hitbox_mode == "hitbox":
        urls = [u for u in urls if "hitbox" in u.lower()]
    elif hitbox_mode == "no-hitbox":
        urls = [u for u in urls if "hitbox" not in u.lower()]

    if not urls:
        print(f"No images found in citizen-section-{section_num}.")
    else:
        print(f"Found {len(urls)} image(s) in citizen-section-{section_num}:\n")
        for url in urls:
            print(url)
        if do_download:
            print()
            download_images(urls, output_dir)


if __name__ == "__main__":
    main()
