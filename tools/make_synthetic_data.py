#!/usr/bin/env python3
"""
Generate a SYNTHETIC school-switch dataset into ../raw/.

WHY THIS EXISTS
---------------
The real municipality extracts are individual-level administrative records for
school pupils and are not redistributable. Without some input data, nobody can
run this repository at all. This script writes a fabricated dataset with the
same folder layout, filenames, column schema and value conventions that both
implementations parse, so the whole pipeline executes end to end.

WHAT THIS IS NOT
----------------
This is NOT a statistical reconstruction of the real data, and results computed
on it will NOT reproduce the paper. Nothing here is estimated, fitted, sampled
or otherwise derived from the real extracts. Every quantity below is either

  (a) already public in the paper -- the six municipality names and the span of
      academic years each one covers; or
  (b) stipulated by hand in the PARAMETERS block, chosen to be round numbers
      that produce a plausible-looking market rather than to match anything.

Consequently the synthetic data cannot leak a distribution, a moment, a count
or a relationship from the real data: no real value was consulted when choosing
the parameters. The cost of that guarantee is that switching rates, the size of
the DA-to-TTC/EADAM gap, and every other output are artefacts of the
stipulations below and carry no substantive meaning.

WHAT IT DOES REPRODUCE
----------------------
Only structure: the file set per municipality, the columns, the id conventions
(participants carry a `switchingFromSchoolProgramId` that is a *school-program*
id resolved to a *school-program-grade* id via the grade), the `rankGroup == 1`
convention marking the submitted rank-ordered list, the OPEN_FOR_REQUESTS
application window, and the rule that a student never ranks their own current
school. Those are the things the loaders depend on.

USAGE
-----
    python3 tools/make_synthetic_data.py            # writes ../raw/
    python3 tools/make_synthetic_data.py --seed 7   # different draw
    python3 tools/make_synthetic_data.py --out /tmp/raw

Deterministic given --seed. Regenerating with the same seed overwrites the
previous output byte for byte.

NOT GENERATED
-------------
The `Test/`, `Test_NonMonotone/` and `Test_BlockingPair/` fixtures used by
`test_mode` are small hand-built worked examples that encode specific
theoretical edge cases. They are not synthesised here: they ship with the
repository in tests/fixtures/. Run them with  python3 tests/run_tests.py
"""

from __future__ import annotations

import argparse
import csv
import random
import uuid
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path

# =============================================================================
# PARAMETERS  -- all hand-stipulated. See "WHAT THIS IS NOT" above.
# =============================================================================

# Municipality names and academic-year spans are the only inputs taken from the
# published paper (Section 2 and Table 1). Everything on the right of the colon
# -- programme counts, participant counts, rounds per year -- is invented, set
# to round numbers that give a spread of market sizes from small to large.
MUNICIPALITIES = {
    # name:          (first_year, last_year, n_schools, participants_per_year, rounds_per_year)
    "Linköping":     (2020, 2025, 60,  700, 3),
    "Malmö":         (2020, 2025, 90, 1100, 2),
    "Nacka":         (2021, 2025, 45,  600, 6),
    "Norrköping":    (2022, 2025, 50,  650, 4),
    "Uppsala":       (2021, 2026, 70,  850, 6),
    "Växjö":         (2023, 2025, 30,  250, 2),
}

GRADES = list(range(0, 10))          # Swedish compulsory school, grades 0-9

# Length of a submitted rank-ordered list. Stipulated; most applicants name one
# or two programmes, a minority name more.
ROL_LENGTH_WEIGHTS = {1: 0.45, 2: 0.28, 3: 0.15, 4: 0.08, 5: 0.04}

# How concentrated demand is across programmes. Programme j in the popularity
# ordering gets weight 1/(j+1)**POPULARITY_EXPONENT. 0 would be uniform demand;
# 1.0 is a moderate Zipf-like skew. Stipulated.
POPULARITY_EXPONENT = 1.0

# Seats recorded on each programme in 2.3 Chooseables. Note that the simulation
# does NOT read these -- effective capacity is derived from how many active
# students currently attend a programme (see the paper, Section 2) -- so the
# value only has to be present and positive.
NOMINAL_CAPACITY = 30

# Academic year y runs 30 June y to 29 June y+1. Application windows are spread
# across the year; each is this many days long. Stipulated.
APPLICATION_WINDOW_DAYS = 21

# Generated placement-round ids start here, chosen to sit well above the
# hard-coded real round ids that both codebases exclude by number
# (config.EXCLUDED_ROUND_IDS / get_data_rounds.py), so no generated round is
# accidentally filtered out.
ROUND_ID_BASE = 9_000_000

MUNICIPALITY_ID_BASE = 900          # arbitrary, only needs to be stable

# =============================================================================


def _stable_uuid(rng: random.Random) -> str:
    """A UUID drawn from `rng`, so output is reproducible for a given seed."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _weighted_choice(rng: random.Random, options, weights):
    return rng.choices(options, weights=weights, k=1)[0]


def _academic_year_bounds(year: int) -> tuple[date, date]:
    """Academic year `year` spans 30 June `year` .. 29 June `year`+1."""
    return date(year, 6, 30), date(year + 1, 6, 29)


def _round_windows(year: int, n_rounds: int) -> list[tuple[datetime, datetime]]:
    """Evenly spaced OPEN_FOR_REQUESTS windows inside the academic year."""
    start, end = _academic_year_bounds(year)
    span = (end - start).days
    step = span // (n_rounds + 1)
    windows = []
    for i in range(1, n_rounds + 1):
        w_start = start + timedelta(days=step * i)
        w_end = w_start + timedelta(days=APPLICATION_WINDOW_DAYS)
        windows.append((datetime.combine(w_start, datetime.min.time()).replace(hour=8),
                        datetime.combine(w_end, datetime.min.time()).replace(hour=23, minute=59)))
    return windows


def _build_programmes(rng: random.Random, n_schools: int):
    """Invent the programme catalogue for one municipality.

    Returns (schools, spgid_of) where
      schools   : list of dicts, one per school, each with a single programme
      spgid_of  : (school_index, grade) -> schoolProgramGradeId
    Popularity rank is assigned once per school and reused across grades, so a
    programme that is in demand at one grade tends to be in demand at others.
    """
    schools = []
    for i in range(n_schools):
        schools.append({
            "school_id": _stable_uuid(rng),
            "school_name": f"Synthetic School {i + 1:03d}",
            "spid": _stable_uuid(rng),              # schoolProgramId
            "program_name": "Synthetic Programme",
            "popularity_rank": i,                   # 0 = most popular
        })
    rng.shuffle(schools)
    for rank, s in enumerate(schools):
        s["popularity_rank"] = rank
    spgid_of = {(i, g): _stable_uuid(rng)
                for i in range(n_schools) for g in GRADES}
    return schools, spgid_of


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def generate_municipality(name: str, spec: tuple, out_root: Path,
                          rng: random.Random) -> dict:
    first_year, last_year, n_schools, per_year, rounds_per_year = spec
    years = list(range(first_year, last_year + 1))
    muni_dir = out_root / name
    # crc32, not hash(): Python's string hash is salted per process, so hash()
    # would change this id on every run and break the byte-identical guarantee.
    municipality_id = MUNICIPALITY_ID_BASE + zlib.crc32(name.encode()) % 100

    schools, spgid_of = _build_programmes(rng, n_schools)
    weights = [1.0 / (s["popularity_rank"] + 1) ** POPULARITY_EXPONENT
               for s in schools]

    rounds_rows, period_rows, choosable_rows, participant_rows = [], [], [], []
    mapping_rows_by_round: dict[int, list[dict]] = {}

    round_id = ROUND_ID_BASE
    n_participants = 0

    for year in years:
        for (w_start, w_end) in _round_windows(year, rounds_per_year):
            round_id += 1
            mapping_rows_by_round[round_id] = []

            rounds_rows.append({
                "placementRoundId": round_id,
                "municipalityId": municipality_id,
                "academicYear": year,
                "roundName": f"Synthetic switch round {round_id}",
                "schoolStartDate": _academic_year_bounds(year)[0].isoformat(),
                "roundType": "SCHOOL_SWITCH",
                "decisionType": "INITIAL_PLACEMENT",
                "hasNotifiedInitialPlacementDecisions": "true",
            })
            # Only OPEN_FOR_REQUESTS is read, but the other stages are written
            # so the file looks like the real thing.
            for stage, s0, s1 in (
                ("OPEN_FOR_REQUESTS", w_start, w_end),
                ("CLOSED_FOR_PLACEMENT", w_end, w_end + timedelta(days=3)),
                ("OPEN_FOR_PLACEMENT_NOTIFICATION", w_end + timedelta(days=3),
                 w_end + timedelta(days=10)),
                ("CLOSED", w_end + timedelta(days=10), w_end + timedelta(days=30)),
            ):
                period_rows.append({
                    "placementRoundId": round_id,
                    "stage": stage,
                    "startPeriod": s0.strftime("%Y-%m-%d %H:%M:%S"),
                    "endPeriod": s1.strftime("%Y-%m-%d %H:%M:%S"),
                })

            # Every programme is choosable in every round, at every grade.
            for i, s in enumerate(schools):
                for g in GRADES:
                    choosable_rows.append({
                        "placementRoundId": round_id,
                        "choosableId": _stable_uuid(rng),
                        "cgy_overrideCapacity": "",
                        "schoolProgramGradeYearId": _stable_uuid(rng),
                        "spgy_capacity": NOMINAL_CAPACITY,
                        "spgy_resevredSeats": 0,
                        "schoolProgramGradeId": spgid_of[(i, g)],
                        "grade": g,
                        "spg_baseCapacity": NOMINAL_CAPACITY,
                        "schoolProgramId": s["spid"],
                        "sp_programName": s["program_name"],
                        "sp_hasSchoolingResponsibility": "true",
                        "sp_isSpecialProgram": "false",
                        "schoolId": s["school_id"],
                        "schoolName": s["school_name"],
                        "s_isVoucherSchool": "false",
                    })

            # --- participants in this round ---------------------------------
            n_this_round = per_year // rounds_per_year
            for _ in range(n_this_round):
                pid = _stable_uuid(rng)
                grade = rng.choice(GRADES)
                current_idx = _weighted_choice(rng, range(n_schools), weights)

                rol_len = _weighted_choice(rng,
                                           list(ROL_LENGTH_WEIGHTS),
                                           list(ROL_LENGTH_WEIGHTS.values()))
                # Draw preferred programmes, excluding the current school: the
                # loaders drop any participant who ranks their own school.
                choices, guard = [], 0
                while len(choices) < rol_len and guard < 200:
                    guard += 1
                    j = _weighted_choice(rng, range(n_schools), weights)
                    if j != current_idx and j not in choices:
                        choices.append(j)
                if not choices:
                    continue

                created = w_start + timedelta(
                    seconds=rng.randrange(int((w_end - w_start).total_seconds())))
                participant_rows.append({
                    "ParticipantId": pid,
                    "placementRoundId": round_id,
                    "studentId": _stable_uuid(rng),
                    "currentChoiceId": _stable_uuid(rng),
                    "switchingFromSchoolProgramId": schools[current_idx]["spid"],
                    "choiceCreatedAt": created.strftime("%Y-%m-%d %H:%M:%S"),
                    "participantType": "InsiderSwitcher",
                })
                n_participants += 1

                # rankGroup == 1 rows ARE the submitted rank-ordered list.
                for rank, j in enumerate(choices, start=1):
                    mapping_rows_by_round[round_id].append({
                        "placementRoundId": round_id,
                        "participantId": pid,
                        "schoolProgramId": schools[j]["spid"],
                        "grade": grade,
                        "ranking": rank,
                        "rankGroup": 1,
                        "rankGroupDescription": "Aktivt val",
                        "distance": round(rng.uniform(0.2, 12.0), 3),
                        "relativeDistance": round(rng.uniform(0.0, 1.0), 4),
                        "priorityGroup": 1,
                    })
                # One rankGroup == 2 row for the current school, so the
                # priority/distance dictionaries have an entry for it. Not part
                # of the ROL.
                mapping_rows_by_round[round_id].append({
                    "placementRoundId": round_id,
                    "participantId": pid,
                    "schoolProgramId": schools[current_idx]["spid"],
                    "grade": grade,
                    "ranking": 0,
                    "rankGroup": 2,
                    "rankGroupDescription": "Nuvarande skola",
                    "distance": round(rng.uniform(0.1, 3.0), 3),
                    "relativeDistance": round(rng.uniform(0.0, 1.0), 4),
                    "priorityGroup": 0,
                })

    _write_csv(muni_dir / "2.1.1 Rundor.csv",
               ["placementRoundId", "municipalityId", "academicYear", "roundName",
                "schoolStartDate", "roundType", "decisionType",
                "hasNotifiedInitialPlacementDecisions"], rounds_rows)
    _write_csv(muni_dir / "2.1.2 PlacementRoundPeriod.csv",
               ["placementRoundId", "stage", "startPeriod", "endPeriod"], period_rows)
    _write_csv(muni_dir / "2.2 Participant.csv",
               ["ParticipantId", "placementRoundId", "studentId", "currentChoiceId",
                "switchingFromSchoolProgramId", "choiceCreatedAt",
                "participantType"], participant_rows)
    _write_csv(muni_dir / "2.3 Chooseables.csv",
               ["placementRoundId", "choosableId", "cgy_overrideCapacity",
                "schoolProgramGradeYearId", "spgy_capacity", "spgy_resevredSeats",
                "schoolProgramGradeId", "grade", "spg_baseCapacity",
                "schoolProgramId", "sp_programName", "sp_hasSchoolingResponsibility",
                "sp_isSpecialProgram", "schoolId", "schoolName",
                "s_isVoucherSchool"], choosable_rows)
    for rid, rows in mapping_rows_by_round.items():
        _write_csv(muni_dir / f"2.4 Participant-PriorityGround - Round {rid}.csv",
                   ["placementRoundId", "participantId", "schoolProgramId", "grade",
                    "ranking", "rankGroup", "rankGroupDescription", "distance",
                    "relativeDistance", "priorityGroup"], rows)

    return {"municipality": name, "years": len(years), "schools": n_schools,
            "rounds": len(rounds_rows), "participants": n_participants}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=20260914,
                    help="RNG seed; same seed gives byte-identical output")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1] / "raw",
                    help="output directory (default: <repo>/raw)")
    args = ap.parse_args()

    print(f"Writing synthetic data to {args.out}  (seed={args.seed})")
    print("NOTE: fabricated data. Parameters are stipulated by hand, not "
          "estimated from the real extracts. Results are meaningless.\n")

    summary = []
    for name, spec in MUNICIPALITIES.items():
        # One RNG per municipality, seeded from the master seed and the name, so
        # regenerating one municipality does not shift the others.
        rng = random.Random(f"{args.seed}:{name}")
        summary.append(generate_municipality(name, spec, args.out, rng))

    w = max(len(s["municipality"]) for s in summary)
    print(f"{'municipality':<{w}}  {'years':>5} {'schools':>8} {'rounds':>7} {'participants':>13}")
    for s in summary:
        print(f"{s['municipality']:<{w}}  {s['years']:>5} {s['schools']:>8} "
              f"{s['rounds']:>7} {s['participants']:>13,}")
    print(f"\n{'TOTAL':<{w}}  {'':>5} {'':>8} "
          f"{sum(s['rounds'] for s in summary):>7} "
          f"{sum(s['participants'] for s in summary):>13,}")


if __name__ == "__main__":
    main()
