"""Reading the data-cleaning exception tables in exclusions/.

`replication_rr` has an equivalent loader in its own config module. The two are
written independently on purpose -- that is the point of shipping two
implementations -- but they read the SAME files, so they cannot disagree about
which records are excluded or remapped.

See exclusions/README.md. The committed CSVs are header-only; a sibling
.local.csv (gitignored) supplies real values when running against real data.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict, List

# This file is at <repo>/original/build/code/functions/, so the repository root
# is four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
EXCLUSIONS_DIR = REPO_ROOT / "exclusions"


def raw_root() -> Path:
    """Directory holding the per-municipality input folders.

    Defaults to raw/ at the repository root, where
    tools/make_synthetic_data.py writes. SCHOOL_SWITCH_RAW_DIR overrides it, so
    real extracts can stay outside the repository; `replication_rr` honours the
    same variable.
    """
    return Path(os.environ.get("SCHOOL_SWITCH_RAW_DIR") or (REPO_ROOT / "raw"))


def _rows(basename: str) -> List[dict]:
    """Rows of exclusions/<basename>, preferring a sibling .local.csv."""
    stem = basename[:-len(".csv")] if basename.endswith(".csv") else basename
    for candidate in (EXCLUSIONS_DIR / f"{stem}.local.csv",
                      EXCLUSIONS_DIR / f"{stem}.csv"):
        if candidate.exists():
            with open(candidate, newline="", encoding="utf-8-sig") as f:
                return [r for r in csv.DictReader(f)
                        if (r.get("municipality") or "").strip()]
    return []


def excluded_round_ids(municipality: str) -> List[int]:
    """Placement-round IDs to drop for this municipality; [] when none."""
    out = []
    for row in _rows("excluded_rounds.csv"):
        if row["municipality"].strip() != municipality:
            continue
        raw = (row.get("placementRoundId") or "").strip()
        if raw:
            out.append(int(raw))
    return out


def _remap(basename: str, old_col: str, new_col: str,
           municipality: str) -> Dict[str, str]:
    out = {}
    for row in _rows(basename):
        if row["municipality"].strip() != municipality:
            continue
        old, new = (row.get(old_col) or "").strip(), (row.get(new_col) or "").strip()
        if old and new:
            out[old] = new
    return out


def spgid_remap(municipality: str) -> Dict[str, str]:
    """Old -> new schoolProgramGradeId for this municipality; {} when none."""
    return _remap("spgid_remap.csv", "old_spgid", "new_spgid", municipality)


def spid_alias(municipality: str) -> Dict[str, str]:
    """Old -> new schoolProgramId for this municipality; {} when none."""
    return _remap("spid_alias.csv", "old_spid", "new_spid", municipality)


def manual_grade_overrides(municipality: str) -> Dict[str, int]:
    """participantId -> grade for this municipality; {} when none.

    Filtered on municipality because a participant id is only unique within one
    municipality's extract.
    """
    out = {}
    for row in _rows("manual_grade_overrides.csv"):
        if row["municipality"].strip() != municipality:
            continue
        pid, grade = (row.get("participantId") or "").strip(), (row.get("grade") or "").strip()
        if pid and grade:
            out[pid] = int(grade)
    return out
