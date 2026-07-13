#!/usr/bin/env python3
"""One-shot migration: scripts/*.json → Supabase works + chapters.

Usage:
  # Dry-run (no network writes) — verifies split/assemble round-trip locally
  python scripts/migrate_to_supabase.py --dry-run

  # Apply (requires SUPABASE_URL + SUPABASE_KEY and applied SQL migration)
  python scripts/migrate_to_supabase.py

Does NOT delete original scripts/*.json files (kept as rollback source).
Prompt templates under prompts/ are intentionally not migrated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from game.content.work_mapper import (  # noqa: E402
    long_form_document_to_rows,
    script_to_work_chapter,
    work_chapter_to_script,
)
from game.db.supabase_client import is_supabase_configured  # noqa: E402

SCRIPTS_DIR = ROOT / "scripts"


def iter_script_files() -> list[Path]:
    return sorted(p for p in SCRIPTS_DIR.rglob("*.json") if p.is_file())


def load_script(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("id"):
        raise ValueError(f"{path}: missing id")
    return data


def compare_round_trip(original: dict, reconstituted: dict) -> list[str]:
    """Return human-readable diffs for keys that matter for gameplay fidelity."""
    # Metadata added by v2 assembler — not required in original flat JSON.
    ignore = {
        "work_type",
        "chapter_id",
        "chapter_title",
        "flags_read",
        "flags_write",
        "exits",
    }
    issues: list[str] = []
    keys = sorted((set(original) | set(reconstituted)) - ignore)
    for key in keys:
        if key not in original:
            issues.append(f"+ extra key after migrate: {key}")
            continue
        if key not in reconstituted:
            issues.append(f"- missing key after migrate: {key}")
            continue
        if original[key] != reconstituted[key]:
            issues.append(f"~ mismatch on {key}")
    return issues


def migrate_one(script: dict, *, dry_run: bool) -> None:
    from game.content.work_mapper import is_long_form_document, long_form_document_to_rows

    if is_long_form_document(script):
        work, chapters = long_form_document_to_rows(script)
        if dry_run:
            print(
                f"  [dry-run] long_form {script['id']} → "
                f"chapters={len(chapters)} entry={work['entry_chapter_id']}"
            )
            return
        from game.content import work_repository

        work_repository.save_long_form_document(script, status="published")
        print(f"  [ok] upserted long_form {script['id']} ({len(chapters)} chapters)")
        return

    work, chapter = script_to_work_chapter(script, work_type="short_form", status="published")
    reconstituted = work_chapter_to_script(work, chapter)
    issues = compare_round_trip(script, reconstituted)
    if issues:
        raise RuntimeError(
            f"Round-trip failed for {script['id']}:\n  " + "\n  ".join(issues)
        )

    if dry_run:
        print(
            f"  [dry-run] {script['id']} → work={work['id']} "
            f"chapter={chapter['id']} extras_keys={sorted(chapter['extras'])}"
        )
        return

    from game.content import work_repository

    work_repository.save_script(script, status="published")
    print(f"  [ok] upserted {script['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate scripts/*.json to Supabase")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate split/assemble only; do not write to Supabase",
    )
    args = parser.parse_args()

    files = iter_script_files()
    if not files:
        print(f"No JSON scripts found under {SCRIPTS_DIR}")
        return 1

    print(f"Found {len(files)} script file(s) under {SCRIPTS_DIR}")

    if not args.dry_run:
        if not is_supabase_configured():
            print(
                "ERROR: SUPABASE_URL and SUPABASE_KEY must be set to run migration.\n"
                "Use --dry-run to validate mapping without a database."
            )
            return 1
        # Force supabase path for writes regardless of CONTENT_BACKEND.
        from game.settings import get_settings

        get_settings.cache_clear()

    failures = 0
    for path in files:
        rel = path.relative_to(ROOT)
        try:
            script = load_script(path)
            print(f"- {rel}")
            migrate_one(script, dry_run=args.dry_run)
        except Exception as exc:
            failures += 1
            print(f"  [FAIL] {rel}: {exc}")

    if failures:
        print(f"\nDone with {failures} failure(s).")
        return 1

    print("\nAll scripts migrated successfully." if not args.dry_run else "\nDry-run OK.")
    print("Original scripts/*.json files were NOT deleted (rollback source).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
