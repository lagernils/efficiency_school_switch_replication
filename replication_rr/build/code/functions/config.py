"""
Municipality-level constants.

Kept in one place so the loading code stays generic. Each block below states
what it excludes or remaps and why.
"""

import csv
import os
from collections import defaultdict
from pathlib import Path


# ---- Paths ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# Input data is shared by both implementations and lives at the repository
# root, one level above this project, so that `original` and `replication_rr`
# are guaranteed to read byte-identical inputs.
REPO_ROOT = PROJECT_ROOT.parent

# Where the input data lives. Defaults to raw/ at the repository root, which is
# where tools/make_synthetic_data.py writes. Set SCHOOL_SWITCH_RAW_DIR to point
# at a directory outside the repository instead -- useful when the real extracts
# live elsewhere and must not be copied in. `original` honours the same variable,
# so both implementations follow one setting.
RAW_DIR = Path(os.environ.get("SCHOOL_SWITCH_RAW_DIR") or (REPO_ROOT / "raw"))

EXCLUSIONS_DIR = REPO_ROOT / "exclusions"
# Hand-built worked examples for test_mode, shipped with the repository.
TEST_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
OUTPUT_DIR = PROJECT_ROOT / "build" / "output" / "loop_results"


def _read_exclusion_rows(basename: str) -> list:
    """Read exclusions/<basename>, preferring a sibling .local.csv if present.

    Returns a list of dict rows, or [] when neither file exists. See
    exclusions/README.md: the committed files are header-only on purpose, and a
    .local.csv (gitignored) supplies the real values when running against real
    data.
    """
    stem = basename[:-len(".csv")] if basename.endswith(".csv") else basename
    for candidate in (EXCLUSIONS_DIR / f"{stem}.local.csv",
                      EXCLUSIONS_DIR / f"{stem}.csv"):
        if candidate.exists():
            with open(candidate, newline="", encoding="utf-8-sig") as f:
                return [r for r in csv.DictReader(f)
                        if (r.get("municipality") or "").strip()]
    return []


# ---- Academic years per municipality ----------------------------------------
ACADEMIC_YEARS = {
    "Malmö":      [2020, 2021, 2022, 2023, 2024, 2025],
    "Linköping":  [2020, 2021, 2022, 2023, 2024, 2025],
    "Nacka":      [2021, 2022, 2023, 2024, 2025],
    "Norrköping": [2022, 2023, 2024, 2025],
    "Uppsala":    [2021, 2022, 2023, 2024, 2025, 2026],
    "Växjö":      [2023, 2024, 2025],
}


# ---- Excluded placement-round IDs -------------------------------------------
# Test rounds, rounds opened and never used, and rounds belonging to a different
# placement process. The identifiers come from the source system, so they live in
# exclusions/excluded_rounds.csv rather than here; that file is header-only in
# this repository. A defaultdict is returned so a municipality with no
# exclusions -- every municipality, on the synthetic dataset -- resolves to an
# empty set rather than raising.
def _load_excluded_round_ids() -> defaultdict:
    out = defaultdict(set)
    for row in _read_exclusion_rows("excluded_rounds.csv"):
        raw = (row.get("placementRoundId") or "").strip()
        if raw:
            out[row["municipality"].strip()].add(int(raw))
    return out


EXCLUDED_ROUND_IDS = _load_excluded_round_ids()


# ---- Reissued school-programme IDs ------------------------------------------
# Some school programmes had their ids reissued mid-sample and must be mapped to
# the current id before any id-keyed structure is built. Same reasoning as above:
# the values are source-system identifiers and live in exclusions/.
def _load_id_remap(basename: str, old_col: str, new_col: str) -> defaultdict:
    out = defaultdict(dict)
    for row in _read_exclusion_rows(basename):
        old, new = (row.get(old_col) or "").strip(), (row.get(new_col) or "").strip()
        if old and new:
            out[row["municipality"].strip()][old] = new
    return out


# Old spgid -> new spgid, per municipality (use before computing any
# spgid-keyed structure).
SPGID_REMAP = _load_id_remap("spgid_remap.csv", "old_spgid", "new_spgid")
# Legacy spid alias used by students' switchingFromSchoolProgramId.
SPID_ALIAS = _load_id_remap("spid_alias.csv", "old_spid", "new_spid")


# ---- Manual multi-grade resolution ------------------------------------------
# A participant can appear at more than one grade in the mapping files. Most are
# resolved automatically from their current school; any that remain ambiguous
# can be resolved by hand in exclusions/manual_grade_overrides.csv (columns:
# municipality, participantId, grade). That file is header-only in this
# repository -- the synthetic dataset never produces an ambiguous participant --
# and, as for the other exception tables, a gitignored .local.csv supplies real
# values. An ambiguous participant with no override is dropped by
# _resolve_grade.
def _load_manual_grade_assignments() -> dict:
    """{(municipality, participantId): grade} from exclusions/manual_grade_overrides[.local].csv."""
    out = {}
    for row in _read_exclusion_rows("manual_grade_overrides.csv"):
        pid, grade = (row.get("participantId") or "").strip(), (row.get("grade") or "").strip()
        if pid and grade:
            out[(row["municipality"].strip(), pid)] = int(grade)
    return out


MANUAL_GRADE_ASSIGNMENTS = _load_manual_grade_assignments()


# ---- Test-mode configuration ------------------------------------------------
# Maps the `which_test_mode` string to its folder under tests/fixtures/ and
# the academic years defined in those tiny hand-built datasets.
TEST_MODE_FOLDERS = {
    "basic":        "Test",
    "nonmonotone":  "Test_NonMonotone",
    "blockingpair": "Test_BlockingPair",
}
TEST_MODE_YEARS = [2021, 2022]       # only one year used when test_mode=True


# ---- Misc numerical constants -----------------------------------------------
LOTTERY_MAX = 10_000_000
# Monte Carlo seed base; iteration i uses SEED_BASE + i. `original` uses the
# same convention and the same per-participant lottery derivation, so an equal
# seed gives both implementations identical lotteries. masterfile.py overrides
# this via the `seed_base` key.
SEED_BASE = 424242
# Seed of the iteration currently being run; set by run_school_switch.run_loop.
# Each student's lottery number is drawn from Random(f"{CURRENT_SEED}:{id}")
# rather than from the shared stream, so it depends only on the seed and the
# participant id -- not on how many numbers were drawn before it. That is what
# lets `original` and `replication_rr` produce identical lotteries.
CURRENT_SEED = SEED_BASE
