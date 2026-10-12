#!/usr/bin/env python3
"""Create smaller WebP alternatives and keep JPEG fallbacks in the HTML."""
from pathlib import Path
import os
import re
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "images"
HTML_FILES = [ROOT / "index.html", *sorted((ROOT / "product").glob("*.html"))]
MAX_EDGE = 1800
QUALITY = 82

def make_webp(source: Path) -> tuple[int, int] | None:
    target = source.with_suffix(".webp")
    original_size = source.stat().st_size
    temporary = target.with_name(target.stem + ".tmp.webp")

    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        if max(image.size) > MAX_EDGE:
            ratio = MAX_EDGE / max(image.size)
            new_size = (max(1, round(image.width * ratio)),
                        max(1, round(image.height * ratio)))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        image.save(temporary, "WEBP", quality=QUALITY, method=6)

    new_size = temporary.stat().st_size
    if new_size >= original_size:
        temporary.unlink(missing_ok=True)
        if target.exists():
            target.unlink()
        return None

    os.replace(temporary, target)
    return original_size, new_size

def add_picture_sources(html: str, page: Path) -> str:
    # Do not wrap images that are already inside a picture element on repeat runs.
    chunks = re.split(r'(<picture\b[^>]*>[\s\S]*?</picture\s*>)', html, flags=re.IGNORECASE)

    def convert_image(match: re.Match) -> str:
        tag = match.group(0)
        src_match = re.search(r'\bsrc\s*=\s*(["\'])(.*?)\1', tag, flags=re.IGNORECASE)
        if not src_match:
            return tag

        src = src_match.group(2)
        if not re.search(r'\.(?:jpe?g)$', src, flags=re.IGNORECASE):
            return tag
        if src.startswith(("http://", "https://", "data:")):
            return tag

        local_source = (page.parent / src).resolve()
        try:
            local_source.relative_to(ROOT.resolve())
        except ValueError:
            return tag

        webp_path = local_source.with_suffix(".webp")
        if not webp_path.is_file():
            return tag

        relative_webp = Path(os.path.relpath(webp_path, page.parent)).as_posix()
        # Preserve image attributes and JPEG as a compatibility fallback.
        return f'<picture><source type="image/webp" srcset="{relative_webp}">{tag}</picture>'

    for index in range(0, len(chunks), 2):
        chunks[index] = re.sub(r'<img\b[^>]*>', convert_image, chunks[index], flags=re.IGNORECASE)
    return "".join(chunks)

def main() -> None:
    sources = sorted([*IMAGE_DIR.glob("*.jpg"), *IMAGE_DIR.glob("*.jpeg"), *IMAGE_DIR.glob("*.JPG")])
    before = after = converted = 0
    for source in sources:
        result = make_webp(source)
        if result:
            original_size, webp_size = result
            before += original_size
            after += webp_size
            converted += 1
            print(f"{source.name}: {original_size:,} -> {webp_size:,} bytes ({100*(1-webp_size/original_size):.1f}% smaller)")
        else:
            print(f"{source.name}: WebP did not reduce size; JPEG kept as-is")

    changed = 0
    for page in HTML_FILES:
        text = page.read_text(encoding="utf-8")
        updated = add_picture_sources(text, page)
        if updated != text:
            page.write_text(updated, encoding="utf-8")
            changed += 1

    saving = (1 - after / before) * 100 if before else 0
    print(f"Converted {converted}/{len(sources)} JPEG files. Converted-image bytes: {before:,} -> {after:,} ({saving:.1f}% smaller).")
    print(f"Updated {changed} HTML files with WebP sources and JPEG fallbacks.")

if __name__ == "__main__":
    main()
