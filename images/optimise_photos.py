#!/usr/bin/env python3
"""
optimise_photos.py
------------------
Batch-compress photos for the dushyantnaresh.com gallery.

Defaults (no arguments needed):
  Source root : ~/Documents/dushyant-website/images
  Output root : ~/Documents/GitHub/dushyantnaresh.com/images

  Source folders processed (preserving subfolder hierarchy):
    images/photography/   → images/photography/
    images/projects/      → images/projects/
    images/site/          → images/site/

  Database: auto-detected photos.json (walked up from output root)

Behaviour:
  - Converts images to WebP at quality 85 (visually lossless)
  - Resizes anything wider than 2400px (aspect ratio preserved)
  - Preserves EXIF metadata in output files (~1 KB overhead)
  - Skips photos already compressed (checks mtime — safe to re-run)
  - Missing output subfolders are created automatically
  - If photos.json is found: appends new entries with EXIF pre-filled,
    existing entries (titles, albums, tags) are never touched
  - Makes a timestamped backup of photos.json before every write

Usage:
    python3 optimise_photos.py
    python3 optimise_photos.py --quality 90
    python3 optimise_photos.py --force
    python3 optimise_photos.py --source-root /other/folder --output-root /other/output
"""

import sys
import json
import re
import shutil
import argparse
from fractions import Fraction
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from PIL import Image, ExifTags
except ImportError:
    print("❌  Pillow is not installed. Run:  python3 -m pip install Pillow")
    sys.exit(1)


# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_SOURCE_ROOT = Path("~/Documents/dushyant-website/images").expanduser()
DEFAULT_OUTPUT_ROOT = Path("~/Documents/GitHub/dushyantnaresh.com/images").expanduser()
SOURCE_FOLDERS      = ["photography", "projects", "site"]
DEFAULT_QUALITY     = 85
MAX_WIDTH           = 2400
SUPPORTED_FORMATS   = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}


# ── EXIF extraction ───────────────────────────────────────────────────────────

def _to_float(val):
    if val is None:
        return None
    try:
        if isinstance(val, tuple) and len(val) == 2:
            return val[0] / val[1] if val[1] else None
        return float(val)
    except Exception:
        return None


def format_focal_length(val):
    fl = _to_float(val)
    return f"{round(fl)}mm" if fl else ""


def format_aperture(val):
    fn = _to_float(val)
    if fn is None:
        return ""
    return f"f/{int(fn)}" if fn == int(fn) else f"f/{fn:.1f}"


def format_shutter_speed(val):
    et = _to_float(val)
    if not et or et <= 0:
        return ""
    if et >= 1:
        return f"{int(et)}s" if et == int(et) else f"{et:.1f}s"
    frac = Fraction(et).limit_denominator(10000)
    return f"{frac.numerator}/{frac.denominator}s"


def extract_exif_metadata(img: Image.Image) -> dict:
    result = {}
    try:
        raw = img._getexif()
        if not raw:
            return result
        named = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()}
        fl = format_focal_length(named.get("FocalLength"))
        fn = format_aperture(named.get("FNumber"))
        et = format_shutter_speed(named.get("ExposureTime"))
        if fl: result["focalLength"]  = fl
        if fn: result["aperture"]     = fn
        if et: result["shutterSpeed"] = et
    except Exception:
        pass
    return result


# ── Image processing ──────────────────────────────────────────────────────────

def correct_orientation(image: Image.Image) -> Image.Image:
    try:
        exif = image._getexif()
        if exif is None:
            return image
        orientation_key = next(
            (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
        )
        if orientation_key and orientation_key in exif:
            for deg, tag_val in [(180, 3), (270, 6), (90, 8)]:
                if exif[orientation_key] == tag_val:
                    image = image.rotate(deg, expand=True)
                    break
    except Exception:
        pass
    return image


def resize_if_needed(image: Image.Image, max_width: int) -> Image.Image:
    w, h = image.size
    if w > max_width:
        image = image.resize((max_width, int(h * (max_width / w))), Image.LANCZOS)
    return image


def get_orientation_label(image: Image.Image) -> str:
    w, h = image.size
    if w > h:  return "landscape"
    if h > w:  return "portrait"
    return "square"


def slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.lower()).strip("-")


def needs_processing(src_path: Path, out_path: Path, force: bool) -> bool:
    """Return True if the file needs to be (re)processed."""
    if force:
        return True
    if not out_path.exists():
        return True
    # Re-process if source is newer than the compressed output
    return src_path.stat().st_mtime > out_path.stat().st_mtime


def optimise_image(src_path, out_dir, quality, max_width, force) -> dict:
    out_path = out_dir / (src_path.stem + ".webp")
    if not needs_processing(src_path, out_path, force):
        return {"status": "skipped", "src": src_path, "out": out_path}
    try:
        with Image.open(src_path) as img:
            exif_bytes  = img.info.get("exif", b"")
            camera_meta = extract_exif_metadata(img)
            if img.mode in ("RGBA", "LA"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img = correct_orientation(img)
            img = resize_if_needed(img, max_width)
            orientation = get_orientation_label(img)
            out_dir.mkdir(parents=True, exist_ok=True)
            save_kwargs = dict(format="WEBP", quality=quality, method=6)
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            img.save(out_path, **save_kwargs)

        original_kb  = src_path.stat().st_size / 1024
        optimised_kb = out_path.stat().st_size  / 1024
        return {
            "status":       "ok",
            "src":          src_path,
            "out":          out_path,
            "original_kb":  original_kb,
            "optimised_kb": optimised_kb,
            "saving_pct":   (1 - optimised_kb / original_kb) * 100 if original_kb else 0,
            "camera_meta":  camera_meta,
            "orientation":  orientation,
        }
    except Exception as exc:
        return {"status": "error", "src": src_path, "error": str(exc)}


def find_images(folder: Path) -> list:
    images = []
    for ext in SUPPORTED_FORMATS:
        images.extend(folder.rglob(f"*{ext}"))
        images.extend(folder.rglob(f"*{ext.upper()}"))
    seen, unique = set(), []
    for p in sorted(images):
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


# ── photos.json helpers ───────────────────────────────────────────────────────

def find_photos_json(output_dir: Path) -> Optional[Path]:
    """Walk up from the output directory looking for photos.json."""
    current = output_dir
    for _ in range(5):
        candidate = current / "photos.json"
        if candidate.exists():
            return candidate
        current = current.parent
    return None


def build_import_entry(result: dict, photos_json_path: Path, order: int) -> dict:
    """Build a photos.json-compatible entry, with src relative to photos.json."""
    out_path  = result["out"]
    site_root = photos_json_path.parent
    try:
        rel_src = str(out_path.relative_to(site_root))
    except ValueError:
        rel_src = out_path.name
    meta = result.get("camera_meta", {})
    return {
        "id":           "photo-" + slug(result["src"].stem),
        "title":        "",
        "album":        "",
        "tags":         [],
        "src":          rel_src,
        "orientation":  result.get("orientation", "landscape"),
        "focalLength":  meta.get("focalLength",  ""),
        "aperture":     meta.get("aperture",     ""),
        "shutterSpeed": meta.get("shutterSpeed", ""),
        "order":        order,
    }


def merge_new_entries(photos_json_path: Path, new_entries: list) -> tuple:
    """
    Append new entries to photos.json, skipping any whose filename already
    exists in the database. Backs up photos.json before writing.
    Returns (added_count, backup_path).
    """
    with open(photos_json_path, encoding="utf-8") as f:
        existing_data = json.load(f)

    existing_photos = existing_data.get("photos", [])
    known_stems     = {Path(p.get("src", "")).stem.lower() for p in existing_photos}
    to_add          = [e for e in new_entries
                       if Path(e.get("src", "")).stem.lower() not in known_stems]

    if not to_add:
        return 0, None

    max_order = max((p.get("order", 0) for p in existing_photos), default=0)
    for i, entry in enumerate(to_add, 1):
        entry["order"] = max_order + i

    ts          = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = photos_json_path.with_name(f"photos.backup-{ts}.json")
    shutil.copy2(photos_json_path, backup_path)

    updated = dict(existing_data)
    updated["photos"] = existing_photos + to_add
    with open(photos_json_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)

    return len(to_add), backup_path


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Optimise photos for dushyantnaresh.com and sync metadata into photos.json."
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT,
                        help=f"Root images folder (default: {DEFAULT_SOURCE_ROOT})")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help=f"Root output folder (default: {DEFAULT_OUTPUT_ROOT})")
    parser.add_argument("--quality",     type=int,  default=DEFAULT_QUALITY, metavar="1-100",
                        help=f"WebP quality (default: {DEFAULT_QUALITY})")
    parser.add_argument("--max-width",   type=int,  default=MAX_WIDTH, metavar="PX",
                        help=f"Maximum image width in pixels (default: {MAX_WIDTH})")
    parser.add_argument("--photos-json", type=Path, default=None, metavar="PATH",
                        help="Path to photos.json (auto-detected if not specified)")
    parser.add_argument("--force", action="store_true",
                        help="Re-process files even if output is newer than source")
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()

    if not source_root.is_dir():
        print(f"❌  Source root not found: {source_root}")
        sys.exit(1)

    # Locate photos.json
    if args.photos_json:
        photos_json_path = args.photos_json.expanduser().resolve()
    else:
        photos_json_path = find_photos_json(output_root)

    print(f"\n📁  Source root : {source_root}")
    print(f"📂  Output root : {output_root}")
    print(f"🎨  Quality     : {args.quality}  (EXIF preserved)")
    print(f"📐  Max width   : {args.max_width}px")
    if photos_json_path and photos_json_path.exists():
        print(f"🗄️   photos.json : {photos_json_path}  (will merge new entries)")
    else:
        print(f"🗄️   photos.json : not found — will write photos_import.json to output root")
    print()

    # Collect all images across all source folders, preserving hierarchy
    all_jobs = []  # list of (src_path, out_dir)
    for folder_name in SOURCE_FOLDERS:
        src_folder = source_root / folder_name
        if not src_folder.is_dir():
            print(f"⚠️   Skipping missing folder: {src_folder}")
            continue
        images = find_images(src_folder)
        for img_path in images:
            # Preserve subfolder structure relative to source_root
            rel = img_path.relative_to(source_root)
            out_dir = output_root / rel.parent
            all_jobs.append((img_path, out_dir))

    if not all_jobs:
        print("ℹ️   No supported images found.")
        sys.exit(0)

    print(f"🔍  Found {len(all_jobs)} image(s) across {SOURCE_FOLDERS}. Processing…\n")

    ok_count    = 0
    skip_count  = 0
    error_count = 0
    total_saved = 0.0
    new_entries = []
    total       = len(all_jobs)

    for i, (img_path, out_dir) in enumerate(all_jobs, 1):
        result = optimise_image(img_path, out_dir, args.quality, args.max_width, args.force)

        if result["status"] == "ok":
            ok_count    += 1
            total_saved += result["original_kb"] - result["optimised_kb"]
            meta         = result["camera_meta"]
            meta_str     = "  ".join(filter(None, [
                meta.get("focalLength"), meta.get("aperture"), meta.get("shutterSpeed")
            ]))
            rel_display = result["src"].relative_to(source_root)
            print(
                f"  [{i:>4}/{total}] ✅  {rel_display}"
                f"  ({result['original_kb']:.0f} KB → {result['optimised_kb']:.0f} KB,"
                f" -{result['saving_pct']:.0f}%)"
                + (f"  [{meta_str}]" if meta_str else "  [no EXIF]")
            )
            if photos_json_path:
                # Only add photography images to photos.json — not projects or site images
                rel = img_path.relative_to(source_root)
                if rel.parts[0] == 'photography':
                    new_entries.append(build_import_entry(result, photos_json_path, i))

        elif result["status"] == "skipped":
            skip_count += 1
            rel_display = img_path.relative_to(source_root)
            print(f"  [{i:>4}/{total}] ⏭️   {rel_display}  (up to date)")

        else:
            error_count += 1
            rel_display = result["src"].relative_to(source_root)
            print(f"  [{i:>4}/{total}] ❌  {rel_display}  ERROR: {result['error']}")

    print(f"""
{'─' * 60}
✨  Done!
   Processed  : {ok_count} image(s)
   Skipped    : {skip_count} image(s)
   Errors     : {error_count} image(s)
   Space saved: {total_saved / 1024:.1f} MB total
{'─' * 60}""")

    if not new_entries:
        print("\n   No new entries to add to the database.\n")
        return

    if photos_json_path and photos_json_path.exists():
        added, backup_path = merge_new_entries(photos_json_path, new_entries)
        if added == 0:
            print(f"\n✔️   All photos already exist in photos.json — nothing to add.\n")
        else:
            print(f"""
📋  photos.json updated  →  {photos_json_path}
    Added  : {added} new entry/entries (EXIF metadata pre-filled)
    Backup : {backup_path}

    Open photo-admin.html, fill in the title and album for the
    new additions, then save.
{'─' * 60}
""")
    else:
        import_path = output_root / "photos_import.json"
        output_root.mkdir(parents=True, exist_ok=True)
        with open(import_path, "w", encoding="utf-8") as f:
            json.dump({"photos": new_entries}, f, indent=2, ensure_ascii=False)
        print(f"""
📋  First run — photos_import.json written to:
    {import_path}

    To set up your database:
      1. Open photo-admin.html and click "Load new file"
      2. Select photos_import.json
      3. Fill in titles, albums, and tags, then click "Save photos.json"

    On every run after that the script will find your photos.json
    and merge new entries automatically.
{'─' * 60}
""")


if __name__ == "__main__":
    main()
