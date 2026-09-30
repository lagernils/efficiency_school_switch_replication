#!/usr/bin/env python3
"""Run both implementations on the three hand-built test fixtures.

    python3 tests/run_tests.py

Each fixture in tests/fixtures/ is a tiny switching market (4 to 10 pupils,
schools "School A" to "School D") small enough to check by hand. For every
fixture this script

  1. runs `replication_rr` and `original` in test mode, one lottery draw, and
     checks that both exit cleanly; and
  2. compares the number of switchers `replication_rr` reports under DA, TTC and
     EADAM with the values recorded below.

The recorded values are a REGRESSION check: they are what this version of the
code produces. A mismatch means behaviour has changed, which may or may not be a
bug. Note that the efficient algorithms (TTC, EADAM) never produce fewer
switchers than DA, as theory requires.

`original` prints every round's placements to the console in test mode -- run
it by hand (see README) to follow an example step by step. Its summary CSVs are
not populated in test mode, so only its exit status is checked here.

Output is written to the usual gitignored build/output/ folders.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# fixture -> {algorithm: (pupils, switchers)} from replication_rr, k = 30 and 90
EXPECTED = {
    "basic":        {"DA": (10, 7), "TTC": (10, 8), "EADAM": (10, 8)},
    "nonmonotone":  {"DA": (6, 3),  "TTC": (6, 3),  "EADAM": (6, 3)},
    "blockingpair": {"DA": (4, 4),  "TTC": (4, 4),  "EADAM": (4, 4)},
}


def _run(project: str, mode: str) -> subprocess.CompletedProcess:
    cfg = {"test_mode": True, "which_test_mode": mode, "n_iterations": 1,
           "randomise_dates": False, "list_of_municipalities": ["Växjö"]}
    env = dict(os.environ, SCHOOL_SWITCH_CONFIG_JSON=json.dumps(cfg))
    return subprocess.run([sys.executable, "main.py"],
                          cwd=REPO / project / "build" / "code",
                          env=env, capture_output=True, text=True)


def _rr_result(algo: str) -> set:
    path = (REPO / "replication_rr" / "build" / "output" / "loop_results"
            / f"summary_stats_{algo}_Växjö.csv")
    with open(path, encoding="utf-8") as f:
        return {(round(float(r["total_students_mean"])),
                 round(float(r["switchers_mean"]))) for r in csv.DictReader(f)}


def main() -> int:
    failures = 0
    for mode, expected in EXPECTED.items():
        print(f"--- {mode} ---")
        for project in ("replication_rr", "original"):
            r = _run(project, mode)
            ok = r.returncode == 0
            print(f"  {project:15} {'runs' if ok else 'FAILED'}")
            if not ok:
                failures += 1
                print("\n".join("    " + line for line in r.stderr.splitlines()[-8:]))
            if project == "replication_rr" and ok:
                for algo, want in expected.items():
                    got = _rr_result(algo)
                    match = got == {want}
                    failures += not match
                    print(f"    {algo:6} pupils/switchers {sorted(got)}"
                          f"{'' if match else f'   expected {want}'}")
    print("\nAll tests passed." if not failures else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
