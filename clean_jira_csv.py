"""
Clean a JIRA CSV export into a compact dataset for RAG ingestion.

Keeps only:
  - Issue key
  - Summary
  - Component
  - Description
  - Comments (JSON list, ordered by column order)

Behavior:
  - Drops rows with missing Issue key or Summary
  - Collapses repeated "Component/s" columns into a single semi-colon separated string
  - Collapses repeated "Comment" columns into a JSON array string (oldest -> newest),
    using column order as the best available ordering signal

Usage (PowerShell):
  python clean_jira_csv.py "C:\\path\\to\\export.csv" "cleaned_jira.csv"
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


NA_VALUES = {"", "na", "n/a", "null", "none", "nan", "(none)"}


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _is_na(s: Optional[str]) -> bool:
    return _norm(s).lower() in NA_VALUES


def _split_components(raw: str) -> List[str]:
    # Components can be separated by comma or semicolon depending on export settings
    parts: List[str] = []
    for chunk in raw.replace(";", ",").split(","):
        v = chunk.strip()
        if v and v.lower() not in NA_VALUES:
            parts.append(v)
    return parts


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _find_column_indexes(header: List[str]) -> Dict[str, List[int]]:
    """
    Returns indexes for:
      - issue_key
      - summary
      - description
      - components (all occurrences)
      - comments (all occurrences)
    """
    # Normalize header entries for matching, but keep indexes for all duplicates
    indexes: Dict[str, List[int]] = {
        "issue_key": [],
        "summary": [],
        "description": [],
        "components": [],
        "comments": [],
    }

    for i, col in enumerate(header):
        c = col.strip()
        cl = c.lower()

        if cl == "issue key":
            indexes["issue_key"].append(i)
        elif cl == "summary":
            indexes["summary"].append(i)
        elif cl == "description":
            indexes["description"].append(i)
        elif cl in {"component/s", "components", "component"}:
            indexes["components"].append(i)
        elif cl == "comment":
            indexes["comments"].append(i)

    return indexes


def clean_csv(input_path: Path, output_path: Path) -> Tuple[int, int]:
    kept = 0
    dropped = 0

    with input_path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f_in:
        reader = csv.reader(f_in)
        header = next(reader, None)
        if not header:
            raise ValueError("CSV appears to be empty (no header row)")

        idx = _find_column_indexes(header)
        if not idx["issue_key"] or not idx["summary"]:
            raise ValueError(
                "Could not find required columns 'Issue key' and 'Summary' in CSV header."
            )

        issue_key_i = idx["issue_key"][0]
        summary_i = idx["summary"][0]
        description_i = idx["description"][0] if idx["description"] else None
        component_is = idx["components"]
        comment_is = idx["comments"]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as f_out:
            writer = csv.writer(f_out)
            writer.writerow(["Issue key", "Summary", "Component", "Description", "Comments"])

            for row in reader:
                # Ensure row long enough
                if len(row) <= max(issue_key_i, summary_i):
                    dropped += 1
                    continue

                issue_key = _norm(row[issue_key_i])
                summary = _norm(row[summary_i])
                if _is_na(issue_key) or _is_na(summary):
                    dropped += 1
                    continue

                description = ""
                if description_i is not None and description_i < len(row):
                    description = _norm(row[description_i])

                # Components: merge all occurrences and de-dupe
                comps: List[str] = []
                for ci in component_is:
                    if ci < len(row):
                        raw = _norm(row[ci])
                        if not _is_na(raw):
                            comps.extend(_split_components(raw))
                comps = _dedupe_preserve_order(comps)
                component_str = "; ".join(comps)

                # Comments: collect all "Comment" columns in header order
                comments: List[str] = []
                for ci in comment_is:
                    if ci < len(row):
                        v = _norm(row[ci])
                        if not _is_na(v):
                            comments.append(v)

                writer.writerow([issue_key, summary, component_str, description, json.dumps(comments)])
                kept += 1

    return kept, dropped


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python clean_jira_csv.py <input.csv> [output.csv]")
        return 2

    input_path = Path(sys.argv[1]).expanduser().resolve()
    if not input_path.exists():
        print(f"[CLEAN] ERROR: input file not found: {input_path}")
        return 2

    output_path = (
        Path(sys.argv[2]).expanduser().resolve()
        if len(sys.argv) >= 3
        else (Path.cwd() / "cleaned_jira.csv").resolve()
    )

    kept, dropped = clean_csv(input_path, output_path)
    print(f"[CLEAN] Wrote: {output_path}")
    print(f"[CLEAN] Rows kept: {kept}")
    print(f"[CLEAN] Rows dropped (missing required fields): {dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

