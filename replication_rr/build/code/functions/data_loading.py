"""
Load raw CSVs for one municipality (or test dataset) into Student/School lists.

Keeps each helper small and focused; the top-level `load_municipality`
orchestrates. The filtering rules (excluded rounds, grade 10+, students who
rank their own current school) are applied here and documented at each site.
"""

from datetime import datetime, date
from pathlib import Path
import os
import random
import numpy as np
import pandas as pd

from .types import Student, School
from . import config


# -----------------------------------------------------------------------------
# File-location helpers
# -----------------------------------------------------------------------------
def _folder_for(municipality: str, test_mode: bool, which_test_mode: str) -> Path:
    if test_mode:
        return config.TEST_FIXTURES_DIR / config.TEST_MODE_FOLDERS[which_test_mode]
    folder = config.RAW_DIR / municipality
    if not folder.exists():
        raise FileNotFoundError(
            "raw data not found at {p}.\nThe real data is not distributed with this package (see raw/README.md).\nRun  python3 tools/make_synthetic_data.py  to create a synthetic dataset,\nor set SCHOOL_SWITCH_RAW_DIR to a directory that holds your own extracts.".format(p=folder))
    return folder


def _file_prefix(test_mode: bool) -> str:
    return "TEST " if test_mode else ""


# -----------------------------------------------------------------------------
# Date parsing
# -----------------------------------------------------------------------------
def _parse_date(raw) -> date:
    """Accept ISO ('2022-06-01 13:00:00') or DD/MM/YYYY formats; NaN -> None."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip().strip('"')
    if s in ("", "NULL", "nan", "NaT"):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Fallback: let pandas try.
    try:
        return pd.to_datetime(s, dayfirst=False).date()
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Round-ID filter
# -----------------------------------------------------------------------------
def _load_rounds(folder: Path, municipality: str, test_mode: bool) -> pd.DataFrame:
    path = folder / f"{_file_prefix(test_mode)}2.1.1 Rundor.csv"
    df = pd.read_csv(path, dtype={"placementRoundId": str})
    df["placementRoundId"] = df["placementRoundId"].astype(str)
    if not test_mode:
        excluded = {str(x) for x in config.EXCLUDED_ROUND_IDS[municipality]}
        df = df[~df["placementRoundId"].isin(excluded)]
    # Only keep school-switch rounds.
    if "roundType" in df.columns:
        df = df[df["roundType"] == "SCHOOL_SWITCH"]
    return df.reset_index(drop=True)


def _load_round_periods(folder: Path, test_mode: bool) -> pd.DataFrame:
    path = folder / f"{_file_prefix(test_mode)}2.1.2 PlacementRoundPeriod.csv"
    df = pd.read_csv(path, dtype={"placementRoundId": str})
    df["placementRoundId"] = df["placementRoundId"].astype(str)
    df["startPeriod"] = df["startPeriod"].apply(_parse_date)
    df["endPeriod"] = df["endPeriod"].apply(_parse_date)
    return df


def _application_window(periods: pd.DataFrame, round_id: str):
    """Return (start, end) of the OPEN_FOR_REQUESTS stage for a raw round."""
    rows = periods[(periods["placementRoundId"] == round_id)
                   & (periods["stage"] == "OPEN_FOR_REQUESTS")]
    if rows.empty:
        return (None, None)
    return (rows["startPeriod"].iloc[0], rows["endPeriod"].iloc[0])


# -----------------------------------------------------------------------------
# Schools (2.3 Chooseables)
# -----------------------------------------------------------------------------
def _load_schools(folder: Path, municipality: str, test_mode: bool,
                  allowed_round_ids: set) -> tuple[dict, dict]:
    """
    Returns (schools_by_spgid_grade, spid_to_spgid_by_grade) restricted to
    rounds in `allowed_round_ids`. Grade 10+ rows are filtered (upper secondary
    is out of scope; this study covers compulsory school, grades 0-9).
    """
    path = folder / f"{_file_prefix(test_mode)}2.3 Chooseables.csv"
    df = pd.read_csv(path, dtype={"placementRoundId": str})
    df["placementRoundId"] = df["placementRoundId"].astype(str)
    df = df[df["placementRoundId"].isin(allowed_round_ids)]
    df = df.dropna(subset=["grade"])
    df = df[df["grade"].astype(int) < 10]              # compulsory school only

    # Some school-program ids were reissued mid-sample and are mapped to the
    # current id here. Empty for every municipality unless
    # exclusions/spgid_remap.csv (or its .local.csv) says otherwise, and
    # .replace({}) is a no-op, so this costs nothing when there is nothing to do.
    df["schoolProgramGradeId"] = df["schoolProgramGradeId"].replace(
        config.SPGID_REMAP.get(municipality, {}))
    df["schoolProgramId"] = df["schoolProgramId"].replace(
        config.SPID_ALIAS.get(municipality, {}))

    schools = {}
    spid_by_grade_to_spgid = {}
    for _, row in df.iterrows():
        grade = int(row["grade"])
        spgid = str(row["schoolProgramGradeId"])
        spid = str(row["schoolProgramId"])
        name = str(row.get("sp_programName", "") or "")
        key = (spgid, grade)
        if key not in schools:
            schools[key] = School(id=spgid, grade=grade, year=0, name=name)
        spid_by_grade_to_spgid[(spid, grade)] = spgid
    return schools, spid_by_grade_to_spgid


# -----------------------------------------------------------------------------
# Students (2.2 Participant) + preferences/priorities (2.4 mapping)
# -----------------------------------------------------------------------------
def _load_participants(folder: Path, municipality: str, test_mode: bool,
                        allowed_round_ids: set) -> pd.DataFrame:
    path = folder / f"{_file_prefix(test_mode)}2.2 Participant.csv"
    df = pd.read_csv(path, dtype={"placementRoundId": str, "studentId": str,
                                  "ParticipantId": str})
    df["placementRoundId"] = df["placementRoundId"].astype(str)
    df = df[df["placementRoundId"].isin(allowed_round_ids)]
    # Normalise NULL strings.
    for col in ("switchingFromSchoolProgramId", "choiceCreatedAt"):
        if col in df.columns:
            df[col] = df[col].replace({"NULL": None, "": None})
    df["choiceCreatedAt"] = df["choiceCreatedAt"].apply(_parse_date)
    if "switchingFromSchoolProgramId" in df.columns:
        df["switchingFromSchoolProgramId"] = df["switchingFromSchoolProgramId"].replace(
            config.SPID_ALIAS.get(municipality, {}))
    return df


def _load_mapping_file(folder: Path, round_id: str, test_mode: bool,
                        municipality: str) -> pd.DataFrame:
    fname = f"{_file_prefix(test_mode)}2.4 Participant-PriorityGround - Round {round_id}.csv"
    path = folder / fname
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"placementRoundId": str, "participantId": str})
    df["placementRoundId"] = df["placementRoundId"].astype(str)
    df = df.dropna(subset=["grade"])
    df["grade"] = df["grade"].astype(int)
    df = df[df["grade"] < 10]                          # compulsory school only
    if "schoolProgramId" in df.columns:
        df["schoolProgramId"] = df["schoolProgramId"].replace(
            config.SPID_ALIAS.get(municipality, {}))
    return df


def _resolve_grade(participant_id: str, mapping_grades: set,
                   current_spid: str, spid_to_spgid_by_grade: dict,
                   municipality: str):
    """Section 5.6: automatic first, then manual override."""
    if len(mapping_grades) == 1:
        return next(iter(mapping_grades))

    # Automatic: current school exists at exactly one of the candidate grades.
    if current_spid:
        hits = [g for g in mapping_grades
                if (current_spid, g) in spid_to_spgid_by_grade]
        if len(hits) == 1:
            return hits[0]

    # Manual override.
    manual = config.MANUAL_GRADE_ASSIGNMENTS.get((municipality, participant_id))
    if manual is not None and manual in mapping_grades:
        return manual

    return None  # caller will drop this student


# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------
def load_municipality(
    municipality: str,
    test_mode: bool = False,
    which_test_mode: str = "basic",
    random_priorities: bool = True,
    unit_demand_mode: bool = False,
    full_consent_bool: bool = True,
) -> tuple[list[Student], list[School], tuple[date, date]]:
    """
    Load and clean one municipality (or test dataset).

    Returns:
        students : list of Student (with raw application_date; no randomisation yet)
        schools  : list of School  (one per (spgid, grade) present in the data)
        (earliest_app, latest_app) : overall application-date bounds, used
                                     for clipping the randomised half-year window.

    Lottery numbers are drawn from Python's stdlib `random` module so that
    seeding via `random.seed(...)` upstream (mirroring `original`) gives the
    two projects a shared RNG family.
    """
    folder = _folder_for(municipality, test_mode, which_test_mode)

    rounds_df = _load_rounds(folder, municipality, test_mode)
    allowed_round_ids = set(rounds_df["placementRoundId"])
    periods_df = _load_round_periods(folder, test_mode)

    schools_dict, spid_to_spgid_by_grade = _load_schools(
        folder, municipality, test_mode, allowed_round_ids)
    participants_df = _load_participants(
        folder, municipality, test_mode, allowed_round_ids)

    # Load all mapping files once (1 per round), concatenated.
    mapping_frames = [
        _load_mapping_file(folder, rid, test_mode, municipality)
        for rid in allowed_round_ids
    ]
    mapping_df = pd.concat([m for m in mapping_frames if not m.empty],
                           ignore_index=True) if mapping_frames else pd.DataFrame()

    if mapping_df.empty:
        return [], list(schools_dict.values()), (None, None)

    # Application-date bounds (used by date randomisation).
    #
    # These come from the OPEN_FOR_REQUESTS windows of the placement rounds, not
    # from the observed choiceCreatedAt values, so that they match `original`'s
    # Get_Students._get_possible_application_dates. The two are not the same
    # quantity -- a round can be open on days nobody applied -- and because the
    # bounds clip the half-year each date is drawn from, using different ones
    # makes the two implementations draw from different windows even when the
    # random offset is identical.
    _starts, _ends = [], []
    for _rid in rounds_df["placementRoundId"].unique():
        _s, _e = _application_window(periods_df, _rid)
        if _s is not None:
            _starts.append(_s)
        if _e is not None:
            _ends.append(_e)
    earliest_app = min(_starts) if _starts else None
    latest_app = max(_ends) if _ends else None

    # Build students
    students = _build_students(
        participants_df, mapping_df, periods_df, rounds_df,
        spid_to_spgid_by_grade, schools_dict,
        municipality, unit_demand_mode, full_consent_bool,
    )

    return students, list(schools_dict.values()), (earliest_app, latest_app)


def _build_students(participants_df, mapping_df, periods_df, rounds_df,
                    spid_to_spgid_by_grade, schools_dict,
                    municipality, unit_demand_mode,
                    full_consent_bool: bool = True):
    # Group mapping rows by participantId.
    by_participant = mapping_df.groupby("participantId")

    # Precompute: application-window end per raw round (fallback for missing dates).
    window_end_by_round = {}
    for rid in rounds_df["placementRoundId"]:
        _, end = _application_window(periods_df, rid)
        window_end_by_round[rid] = end

    # `lottery_number` may exist in test data; otherwise we draw one ourselves.
    has_lottery_col = "lottery_number" in participants_df.columns

    students = []
    for _, part in participants_df.iterrows():
        pid = str(part["ParticipantId"])
        if pid not in by_participant.groups:
            continue
        rows = by_participant.get_group(pid)

        # Grade resolution.
        grades = set(int(g) for g in rows["grade"].unique())
        current_spid = part.get("switchingFromSchoolProgramId")
        if pd.isna(current_spid):
            current_spid = None
        elif current_spid is not None:
            current_spid = str(current_spid)
        grade = _resolve_grade(pid, grades, current_spid,
                                spid_to_spgid_by_grade, municipality)
        if grade is None:
            continue
        rows = rows[rows["grade"] == grade]

        # Map current school (spid) -> spgid at this grade.
        current_school_spgid = None
        if current_spid is not None:
            current_school_spgid = spid_to_spgid_by_grade.get(
                (current_spid, grade))
        if current_school_spgid is None:
            continue                    # ranks own current school; see below

        # Preferences: ranked rows only, sorted by `ranking`, mapped to spgid.
        ranked = rows[rows["rankGroup"] == 1].sort_values("ranking")
        prefs = []
        for _, r in ranked.iterrows():
            spid = str(r["schoolProgramId"])
            spgid = spid_to_spgid_by_grade.get((spid, grade))
            if spgid is not None and (spgid, grade) in schools_dict:
                prefs.append(spgid)
        # Drop duplicates while preserving order.
        seen = set()
        prefs = [p for p in prefs if not (p in seen or seen.add(p))]

        # Unit-demand mode: only the first preference counts.
        if unit_demand_mode and prefs:
            prefs = prefs[:1]

        # Current school must not be ranked: bounce-back appends it later, and
        # a student who ranked it explicitly would get it twice.
        if current_school_spgid in prefs:
            continue
        if not prefs:
            continue

        # Application date (raw). Fall back to round's application-window end.
        app_date = part["choiceCreatedAt"]
        if app_date is None:
            app_date = window_end_by_round.get(str(part["placementRoundId"]))
        if app_date is None:
            continue

        lottery = int(part["lottery_number"]) if has_lottery_col \
            else random.Random(f'{config.CURRENT_SEED}:{part["ParticipantId"]}').randint(1, config.LOTTERY_MAX)

        year = app_date.year if app_date >= date(app_date.year, 6, 30) \
            else app_date.year - 1

        students.append(Student(
            id=str(part["ParticipantId"]),          # <-- switched from studentId
            grade=grade,
            year=year,
            current_school=current_school_spgid,
            preferences=prefs,
            lottery_number=lottery,
            application_date=app_date,
            studentid=str(part["studentId"]),
            consent=1 if full_consent_bool else 0,
        ))
    return students
