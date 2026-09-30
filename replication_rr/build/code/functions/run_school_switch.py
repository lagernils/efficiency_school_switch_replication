"""
High-level driver: runs the Monte Carlo loop for one municipality.

Public API:
    Run_School_Switch().run_loop(
        n_iterations, test_mode, which_test_mode, unit_demand_mode,
        base_capacity, randomise_dates, random_priorities,
        municipality, full_consent_bool=True, lite_mode=False,
        overcapacity_pct=None, demand_proportional_capacity=False,
    )
"""

from copy import deepcopy
from pathlib import Path
import csv
import random
import numpy as np
import pandas as pd

from . import config
from .data_loading import load_municipality
from .preprocessing import (
    randomise_application_dates, append_bounce_back, assign_priority_ranks,
)
from .adapted_rounds import build_adapted_rounds, assign_students_to_rounds
from .dynamic import run_dynamic, allocate_extra_seats
from .stats import compute_stats_for_market
from .aggregation import combine_markets, summarise_iterations


# Default run frequencies when main.py is invoked standalone. masterfile.py
# overrides this via the `k_intervals` key -- the paper uses
# [10, 30, 60, 90, 120, 180, 365] in standard mode and a single k in the
# capacity loop.
K_INTERVALS = [30, 90]


ALGOS = ("DA", "TTC", "EADAM")


class Run_School_Switch:
    def run_loop(self,
                 n_iterations: int,
                 test_mode: bool,
                 which_test_mode: str,
                 unit_demand_mode: bool,
                 base_capacity: int,
                 randomise_dates: bool,
                 random_priorities: bool,
                 municipality: str,
                 full_consent_bool: bool = True,
                 lite_mode: bool = False,
                 overcapacity_pct: float | None = None,
                 demand_proportional_capacity: bool = False):
        """When `lite_mode` is True, skip the standard per-muni CSV writes and
        return the summarised dict per algo so the caller can write a single
        combined CSV. Used by masterfile.py's overcapacity loop.

        `overcapacity_pct` (see main.py's OVERCAPACITY_PCT) is the
        number of additional empty seats to add, expressed as a percentage of
        the active students in each (year, grade) market. When it is None the
        old `base_capacity` rule applies instead -- the same integer number of
        seats at every school -- so leaving it unset reproduces the paper's
        baseline exactly. `demand_proportional_capacity` selects how the
        budget is spread across programs; see dynamic.py:allocate_extra_seats."""
        print(f"[{municipality}] starting ({n_iterations} iterations, "
              f"k={K_INTERVALS}, test_mode={test_mode}, "
              f"full_consent_bool={full_consent_bool}, lite_mode={lite_mode})")

        runs_by_algo_by_k = {algo: {k: [] for k in K_INTERVALS} for algo in ALGOS}

        for it in range(n_iterations):
            seed = config.SEED_BASE + it
            # Iteration-scoped seeding. Mirror `original` exactly: seed both
            # Python's stdlib `random` (used for lottery + date draws) and
            # numpy's legacy seed (in case any module reaches for np.random.*
            # directly). Re-seeding per iteration re-draws lottery numbers and
            # application dates.
            random.seed(seed)
            np.random.seed(seed)
            config.CURRENT_SEED = seed
            students_raw, schools, (min_date, max_date) = load_municipality(
                municipality, test_mode=test_mode,
                which_test_mode=which_test_mode,
                random_priorities=random_priorities,
                unit_demand_mode=unit_demand_mode,
                full_consent_bool=full_consent_bool,
            )
            if randomise_dates:
                randomise_application_dates(
                    students_raw, min_date, max_date)

            # Diagnostic: per-(year, grade) unique-program count for this muni.
            # Computed once, on iteration 0 (the count is data/bucketing-dependent,
            # not algo/k-dependent, so one iteration is enough). Used by
            # masterfile.py's basecapacity loop to compute % overcapacity.
            if it == 0:
                self._append_unique_programs_diagnostic(
                    students_raw, municipality,
                    test_mode=test_mode, lite_mode=lite_mode,
                    demand_proportional_capacity=demand_proportional_capacity)

            # Run DA, TTC and EADAM with identical inputs within an iteration (paired).
            for algo in ALGOS:
                for k in K_INTERVALS:
                    students = deepcopy(students_raw)
                    market_stats = self._run_one_config(
                        students, schools, k, base_capacity, algo,
                        test_mode=test_mode, municipality=municipality,
                        overcapacity_pct=overcapacity_pct,
                        demand_proportional_capacity=demand_proportional_capacity,
                    )
                    runs_by_algo_by_k[algo][k].append(
                        combine_markets(market_stats))
            print(f"  iteration {it+1}/{n_iterations} done")

        # Per-municipality summarised stats (mean/std across iterations).
        per_algo_summaries = {algo: summarise_iterations(runs_by_algo_by_k[algo])
                              for algo in ALGOS}

        if lite_mode:
            # Skip standard per-muni CSV writes; caller will collect the
            # returned dict across munis and write a single combined CSV.
            return per_algo_summaries

        for algo, df in per_algo_summaries.items():
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = config.OUTPUT_DIR / f"summary_stats_{algo}_{municipality}.csv"
            df.to_csv(out_path, index=False)
            print(f"  wrote {out_path.name}")

    # -------------------------------------------------------------------------
    # Per-(muni, year, grade) unique-program-count diagnostic.
    # File: <project>/build/output/diagnostic_unique_programs.csv
    # Cleared once (header rewritten) the first time this method writes to a
    # given output path in a given Python process; appended to thereafter, so
    # each file ends up holding one row per (muni, year, grade) across all
    # munis run in this process. Tracked per-path (not a single shared flag)
    # so that switching demand_proportional_capacity mid-process -- which
    # routes to a different subfolder -- doesn't skip the header write for
    # whichever path is touched second.
    # -------------------------------------------------------------------------
    _diagnostic_initialised_paths: set = set()

    def _append_unique_programs_diagnostic(self, students, municipality,
                                            test_mode, lite_mode=False,
                                            demand_proportional_capacity=False):
        years = (config.TEST_MODE_YEARS if test_mode
                  else config.ACADEMIC_YEARS.get(municipality, []))
        rows = []
        for year in years:
            grades = sorted({s.grade for s in students if s.year == year})
            for grade in grades:
                group = [s for s in students if s.year == year and s.grade == grade]
                if not group:
                    continue
                unique_progs = set()
                for s in group:
                    unique_progs.update(s.preferences)
                rows.append([municipality, year, grade, len(group), len(unique_progs)])

        # In lite (overcapacity-loop) mode, route the diagnostic to the
        # build/output/overcapacity/ folder (or overcapacity_demandprop/ when
        # demand_proportional_capacity is on, so the two counterfactuals never
        # overwrite each other's cached data); otherwise keep it next to
        # loop_results/.
        if lite_mode:
            subfolder = "overcapacity_demandprop" if demand_proportional_capacity else "overcapacity"
            diag_path = config.OUTPUT_DIR.parent / subfolder / "diagnostic_unique_programs.csv"
        else:
            diag_path = config.OUTPUT_DIR.parent / "diagnostic_unique_programs.csv"
        diag_path.parent.mkdir(parents=True, exist_ok=True)
        first_call = diag_path not in Run_School_Switch._diagnostic_initialised_paths
        mode = "w" if first_call else "a"
        with open(diag_path, mode, newline="") as f:
            w = csv.writer(f)
            if first_call:
                w.writerow(["muni", "year", "grade", "n_students", "n_unique_programs"])
                Run_School_Switch._diagnostic_initialised_paths.add(diag_path)
            w.writerows(rows)

    # -------------------------------------------------------------------------
    # One (year, grade, k, algorithm, iteration) run
    # -------------------------------------------------------------------------
    def _run_one_config(self, students, schools, k, base_capacity, algo,
                         test_mode, municipality,
                         overcapacity_pct=None,
                         demand_proportional_capacity=False):
        # Filter to academic years this municipality covers.
        years = (config.TEST_MODE_YEARS if test_mode
                  else config.ACADEMIC_YEARS[municipality])
        students = [s for s in students if s.year in years]

        # Append bounce-back, assign priority ranks (per market).
        market_stats = []
        for year in years:
            grades_present = {s.grade for s in students if s.year == year}
            for grade in sorted(grades_present):
                group = [s for s in students if s.year == year and s.grade == grade]
                if not group:
                    continue
                # The extra-seat budget for this market is fixed here,
                # once, BEFORE append_bounce_back (which would otherwise add
                # each student's current school to their list and count it as
                # demand) and outside the per-round and per-algorithm loops, so
                # DA, TTC and EADAM all face exactly the same capacities and
                # the allocation does not move with the Monte Carlo draw.
                extra_seats = (None if overcapacity_pct is None
                               else allocate_extra_seats(
                                   group, overcapacity_pct,
                                   demand_proportional_capacity))

                # Bounce-back and priority ranks depend only on the group.
                append_bounce_back(group)
                assign_priority_ranks(group)

                adapted_rounds = build_adapted_rounds(year, grade, k)
                assigned = assign_students_to_rounds(group, adapted_rounds)
                placements, cutoffs, _ = run_dynamic(
                    adapted_rounds, base_capacity, algo,
                    extra_seats=extra_seats)
                stats = compute_stats_for_market(
                    assigned, placements, cutoffs, adapted_rounds)
                market_stats.append(stats)
        return market_stats
