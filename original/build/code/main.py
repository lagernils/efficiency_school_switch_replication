# Own modules
from functions.get_data import Get_Data
from functions.get_data_impl import get_data_students
from functions.get_adapted_rounds import Get_Adapted_Rounds
from functions.get_dynamic_round import Generate_Dynamic_Round
from functions.main_helper import Helper
from functions.update_round import Update_Round, allocate_extra_seats
from functions.get_dynamic_DA import Dynamic_DA
from functions.get_dynamic_TTC import Dynamic_TTC
from functions.get_dynamic_EADAM import Dynamic_EADAM
from functions.get_stats import Get_Stats
# External packages
from operator import itemgetter
import os
import random
import csv
import statistics
from pathlib import Path
import numpy as np

# Set seeds for reproducibility
os.environ.setdefault('PYTHONHASHSEED', '1982')
random.seed(1982)
np.random.seed(1982)

class Run_School_Switch:
    k_intervals = [10, 30, 90, 180, 365]

    # Per-process guard for the unique-program diagnostic CSV: only the first
    # call truncates+writes header, subsequent calls append. The set holds
    # municipalities already written so we emit at most once per muni per process.
    _diagnostic_initialised = False
    _diagnostic_munis_done = set()

    def run(self, algo_str: str, test_mode: bool, which_test_mode:str, unit_demand_mode: bool, base_capacity: int, randomise_dates: bool, random_priorities: bool = False, municipality: str = 'Malmö', full_consent_bool: bool = True, lite_mode: bool = False, overcapacity_pct=None, demand_proportional_capacity: bool = False) -> None:

        # Placement settings
        self.algo_str = algo_str
        self.base_capacity = base_capacity
        self.test_mode = test_mode
        self.municipality = municipality
        self.full_consent_bool = full_consent_bool
        self.lite_mode = lite_mode
        # When overcapacity_pct is None the old base_capacity rule
        # applies and results are the paper's baseline.
        self.overcapacity_pct = overcapacity_pct
        # (year, grade, spgid) -> extra seats, filled in by _get_placements
        # and handed to Helper().check_capacity_constraints so the no-slack
        # invariant is relaxed by exactly each school's own allowance.
        self._extra_by_school = {}
        self.demand_proportional_capacity = demand_proportional_capacity

        # Placement round specifications
        self.years = Helper().get_years(municipality)
        self.stats = Helper().get_empty_stats_dict(self.years, self.k_intervals)

        # Get underlying data
        input_data = Get_Data().get(test_mode, which_test_mode, unit_demand_mode, self.years, randomise_dates, municipality, full_consent_bool)
        print("Data retrieval complete.")

        for k in self.k_intervals:
            # Adapt placement rounds using helper (also get final application end date)
            adapted_rounds, final_placement_dates = Get_Adapted_Rounds().get(input_data['placementrounds'], k, self.years)

            # Generate dynamic rounds and allow adjustments to students/schools
            dynamic_round_data = Generate_Dynamic_Round().get(input_data['students'], input_data['schools'], adapted_rounds, random_priorities)
            all_students, all_schools, year_grade_to_pr_to_students, year_grade_to_pr_to_schools = itemgetter(
                'students','schools','year_grade_to_pr_to_students','year_grade_to_pr_to_schools')(dynamic_round_data)
            for school in all_schools:
                school.placed_studentobjs = [] # Reset placed_studentobjs to ensure clean slate for placements
            # Loop over years and grades to run dynamic DA or TTC
            if not self.test_mode:
                self._get_placements(k, adapted_rounds, final_placement_dates, all_students, all_schools, year_grade_to_pr_to_students, year_grade_to_pr_to_schools)
                print(f"Placement for all grades and years with k={k} completed. ")
            else:
                self._get_placements_testmode(k, adapted_rounds, final_placement_dates, all_students, all_schools, year_grade_to_pr_to_students, year_grade_to_pr_to_schools)
            print('Checking capacity constraints for all schools for k ={k}...')
            Helper().check_capacity_constraints(
                all_students, all_schools,
                self._extra_by_school if self.overcapacity_pct is not None else None,
                self.base_capacity)
            print("Capacity constraints verified.")
            if algo_str == 'DA':
                print(f"Dynamic Deferred Acceptance algorithm for all grades completed for k={k}. Output saved.")
            elif algo_str == 'TTC':
                print(f"Dynamic Top Trading Cycles algorithm for all grades completed for k={k}. Output saved.")
            elif algo_str == 'EADAM':
                print(f"Dynamic EADAM algorithm for all grades completed for k={k}. Output saved.")

        print("All done.")
        stats_by_k = Helper().print_all_stats(self.stats, self.k_intervals, test_mode)
        ## self._save_summary_stats_csv(stats_by_k)
        return stats_by_k

    def _save_summary_stats_csv(self, stats_by_k) -> None:
        outdir = Path(__file__).resolve().parents[2] / 'build' / 'output'
        outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / f'summary_stats_{self.algo_str}.csv'
        stat_keys = list(next(iter(stats_by_k.values())).keys())
        with open(outpath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['k'] + stat_keys)
            for k in self.k_intervals:
                writer.writerow([k] + [stats_by_k[k][key] for key in stat_keys])
        print(f"Wrote summary stats to {outpath}")

    def run_loop(self, n_iterations: int, test_mode: bool, which_test_mode: str, unit_demand_mode: bool, base_capacity: int, randomise_dates: bool, random_priorities: bool = False, algos=('TTC', 'DA', 'EADAM'), seed_base: int = 0, municipality: str = 'Malmö', full_consent_bool: bool = True, lite_mode: bool = False, overcapacity_pct=None, demand_proportional_capacity: bool = False) -> dict:
        """Run Run_School_Switch.run() n_iterations times per algorithm with re-drawn lotteries and randomised dates.
        Paired seeding: within each iteration, DA, TTC and EADAM see the same random draws.
        When `lite_mode` is True, skip the per-muni CSV writes and return the
        per-iteration stats so the caller can write a single combined CSV."""
        self.municipality = municipality
        results = {algo: [] for algo in algos}
        for i in range(n_iterations):
            for algo in algos:
                random.seed(seed_base + i)
                np.random.seed(seed_base + i)
                get_data_students.CURRENT_SEED = seed_base + i
                stats_by_k = Run_School_Switch().run(algo, test_mode, which_test_mode, unit_demand_mode, base_capacity, randomise_dates, random_priorities, municipality, full_consent_bool, lite_mode=lite_mode, overcapacity_pct=overcapacity_pct, demand_proportional_capacity=demand_proportional_capacity)
                results[algo].append(stats_by_k)
            print(f"Iteration {i + 1}/{n_iterations} complete.")
        if lite_mode:
            return results   # caller writes the combined CSV; skip per-muni writes
        for algo in algos:
            self._save_loop_csv(algo, results[algo])
        return results

    def _save_loop_csv(self, algo: str, per_iter_stats: list) -> None:
        outdir = Path(__file__).resolve().parents[2] / 'build' / 'output' / 'loop_results'
        outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / f'summary_stats_{algo}_{self.municipality}.csv'
        stat_keys = list(next(iter(per_iter_stats[0].values())).keys())
        with open(outpath, 'w', newline='') as f:
            writer = csv.writer(f)
            header = ['k']
            for key in stat_keys:
                header += [f'{key}_mean', f'{key}_std']
            writer.writerow(header)
            for k in self.k_intervals:
                row = [k]
                for key in stat_keys:
                    values = [d[k][key] for d in per_iter_stats]
                    m = statistics.mean(values)
                    s = statistics.stdev(values) if len(values) > 1 else 0.0
                    row += [round(m, 4), round(s, 4)]
                writer.writerow(row)
        print(f"Wrote loop summary stats ({len(per_iter_stats)} iterations) to {outpath}")

    @staticmethod
    def _market_students(pr_to_students) -> list:
        """Unique students in one (year, grade) market, flattened across the
        placement rounds they arrive in. Used both by the unique-programs
        diagnostic and by the extra-seat allocation, so the two always
        agree on what "the students in this market" means."""
        seen, out = set(), []
        for students in pr_to_students.values():
            for st in students:
                if st.idx not in seen:
                    seen.add(st.idx)
                    out.append(st)
        return out

    def _emit_unique_programs_diagnostic(self, year_grade_to_pr_to_students) -> None:
        """One-time-per-muni-per-process: write rows
            (muni, year, grade, n_students, n_unique_programs)
        to build/output/diagnostic_unique_programs.csv (or the overcapacity
        subfolder when in lite mode). Used by masterfile.py's capacity loop."""
        if self.municipality in Run_School_Switch._diagnostic_munis_done:
            return
        rows = []
        for year in self.years:
            for grade in range(0, 10):
                pr_to_students = year_grade_to_pr_to_students[year].get(grade, {})
                # Flatten across placement rounds: collect every student that
                # falls into this (year, grade) market.
                students_in_market = set()
                for pr_id, students in pr_to_students.items():
                    for s in students:
                        students_in_market.add(s.idx)
                if not students_in_market:
                    continue
                actual_students = self._market_students(pr_to_students)
                unique_progs = set()
                for s in actual_students:
                    unique_progs.update(s.complete_preferences or [])
                rows.append([self.municipality, year, grade,
                             len(actual_students), len(unique_progs)])

        outdir = Path(__file__).resolve().parents[2] / 'build' / 'output'
        if self.lite_mode:
            outdir = outdir / ('overcapacity_demandprop'
                               if self.demand_proportional_capacity else 'overcapacity')
        outdir.mkdir(parents=True, exist_ok=True)
        diag_path = outdir / 'diagnostic_unique_programs.csv'
        first_call = not Run_School_Switch._diagnostic_initialised
        mode = 'w' if first_call else 'a'
        with open(diag_path, mode, newline='') as f:
            w = csv.writer(f)
            if first_call:
                w.writerow(['muni', 'year', 'grade', 'n_students', 'n_unique_programs'])
                Run_School_Switch._diagnostic_initialised = True
            w.writerows(rows)
        Run_School_Switch._diagnostic_munis_done.add(self.municipality)

    def _get_placements(self, k, adapted_rounds, final_placement_dates, all_students, all_schools, year_grade_to_pr_to_students, year_grade_to_pr_to_schools) -> None:
        # One-shot diagnostic: unique-programs count per (year, grade) market.
        self._emit_unique_programs_diagnostic(year_grade_to_pr_to_students)
        for year in self.years:
            for grade in range(0,10):
                nr_students = len(year_grade_to_pr_to_students[year][grade])
                if nr_students:
                    # Fix this market's extra-seat budget ONCE, before
                    # the round loop and outside the algorithm choice, so DA,
                    # TTC and EADAM all face identical capacities and the
                    # allocation does not move with the Monte Carlo draw.
                    extra_seats = None
                    if self.overcapacity_pct is not None:
                        extra_seats = allocate_extra_seats(
                            self._market_students(year_grade_to_pr_to_students[year][grade]),
                            self.overcapacity_pct,
                            self.demand_proportional_capacity)
                    if extra_seats is not None:
                        for _schools in year_grade_to_pr_to_schools[year][grade].values():
                            for _s in _schools:
                                self._extra_by_school[(year, grade, _s.spgid)] = \
                                    extra_seats.get(_s.spgid, 0)
                            break
                    if self.algo_str == 'DA':
                        Dynamic_DA().run(grade, year_grade_to_pr_to_students[year], year_grade_to_pr_to_schools[year], adapted_rounds[year][grade], self.base_capacity, self.test_mode, extra_seats)
                    elif self.algo_str == 'TTC':
                        Dynamic_TTC().run(grade, year_grade_to_pr_to_students[year], year_grade_to_pr_to_schools[year], adapted_rounds[year][grade], self.base_capacity, self.test_mode, extra_seats)
                    elif self.algo_str == 'EADAM':
                        Dynamic_EADAM().run(grade, year_grade_to_pr_to_students[year], year_grade_to_pr_to_schools[year], adapted_rounds[year][grade], self.base_capacity, self.test_mode, extra_seats)
                    else:
                        raise ValueError(f"Unknown algorithm choice: {self.algo_str}")
                    students_in_year_grade = [student for student in all_students if student.grade == grade and student.year == year]
                    schools_in_year_grade = [school for school in all_schools if school.grade == grade and school.year == year]
                    print(f"Completed placement for grade {grade} in year {year} with k={k} and {nr_students} students.")
                    self.stats[year][k][grade] = Get_Stats().get(students_in_year_grade, schools_in_year_grade, final_placement_dates[year])

    def _get_placements_testmode(self, k, adapted_rounds, final_placement_dates, all_students, all_schools, year_grade_to_pr_to_students, year_grade_to_pr_to_schools) -> None:
        print("Running test mode placement for grade 0 only...")
        for year in self.years:
            if year in [2021]:
                if self.algo_str == 'DA':
                    Dynamic_DA().run(0, year_grade_to_pr_to_students[year], year_grade_to_pr_to_schools[year], adapted_rounds[year][0], self.base_capacity, self.test_mode)
                elif self.algo_str == 'TTC':
                    Dynamic_TTC().run(0, year_grade_to_pr_to_students[year], year_grade_to_pr_to_schools[year], adapted_rounds[year][0], self.base_capacity, self.test_mode)
                elif self.algo_str == 'EADAM':
                    Dynamic_EADAM().run(0, year_grade_to_pr_to_students[year], year_grade_to_pr_to_schools[year], adapted_rounds[year][0], self.base_capacity, self.test_mode)
                else:
                    raise ValueError(f"Unknown algorithm choice: {self.algo_str}")
                students_in_year_grade = [student for student in all_students if student.grade == 0 and student.year == year]
                schools_in_year_grade = [school for school in all_schools if school.grade == 0 and school.year == year]
                print(f"Completed DA for grade 0 in year {year} with k={k}.")
                self.stats[year][k][0] = Get_Stats().get(students_in_year_grade, schools_in_year_grade, final_placement_dates[year])
    
test_mode = False
which_test_mode = 'basic' # 'basic' or 'nonmonotone' or 'blockingpair'
unit_demand_mode = False
randomise_dates = True if not test_mode else False
base_capacity = 0 # Set base capacity for schools

# Additional empty seats as a PERCENTAGE OF ACTIVE STUDENTS in each
# (year, grade) market, which is exactly the quantity on the x-axis of the
# capacity figure. In each market the budget is round(OVERCAPACITY_PCT/100 *
# n_students), handed out across the programs appearing in at least one ROL,
# using largest-remainder rounding so the total is hit exactly.
#
# Leave as None to fall back on the `base_capacity` rule above (the same integer
# number of seats at every school), which is what the paper's baseline and the
# k-sensitivity results use. masterfile.py's overcapacity loop sets it to
# 0, 5, 10, ... 100 in turn.
#
# ADD_CAPACITIES_BY_DEMAND selects how that budget is spread: False splits it
# evenly across programs, True in proportion to how many students rank each.
# See functions/update_round.py:allocate_extra_seats.
OVERCAPACITY_PCT = None
ADD_CAPACITIES_BY_DEMAND = False
random_priorities = True # If True, replace priorities with single-tiebreaker lottery (lottery_number only)
n_iterations = 3 # Number of iterations to run in loop mode (with re-drawn lotteries and randomised dates each time)
# Monte Carlo seed base; iteration i uses seed_base + i. `replication_rr` uses
# the same convention (functions/config.py:SEED_BASE) and the same
# per-participant lottery derivation, so an equal seed gives both
# implementations identical lotteries. masterfile.py overrides this.
seed_base = 424242
full_consent_bool = True # If True, all students consent (EADAM = StuOLA); if False, no students consent (EADAM = DA)
#municipality = 'Nacka'
list_of_municipalities = ['Linköping','Malmö','Nacka', 'Norrköping','Uppsala','Växjö']

# If invoked via ../../../masterfile.py, override the defaults above from the env var.
import json as _json
_override = _json.loads(os.environ.get('SCHOOL_SWITCH_CONFIG_JSON', '{}'))
for _k, _v in _override.items():
    if _k in globals():
        globals()[_k] = _v
    elif hasattr(Run_School_Switch, _k):   # e.g. class attribute `k_intervals`
        setattr(Run_School_Switch, _k, _v)

lite_mode = bool(_override.get('lite_mode', False))


def _run_lite_mode():
    """Basecapacity-loop output path: collect per-muni summarised stats and
    write a single combined CSV per subprocess (one row per muni-algo-k).
    Skips the per-muni and ALL CSVs, and Helper.summarise_across_municipalities."""
    subfolder = 'overcapacity_demandprop' if ADD_CAPACITIES_BY_DEMAND else 'overcapacity'
    out_dir = Path(__file__).resolve().parents[2] / 'build' / 'output' / subfolder
    out_dir.mkdir(parents=True, exist_ok=True)
    x_value = 0 if OVERCAPACITY_PCT is None else OVERCAPACITY_PCT
    out_path = out_dir / f'run_x{x_value:g}.csv'

    # Column-name mapping (original uses "percent_*", we publish a unified schema).
    rows = []
    for municipality in list_of_municipalities:
        per_algo_iters = Run_School_Switch().run_loop(
            n_iterations, test_mode, which_test_mode, unit_demand_mode,
            base_capacity, randomise_dates, random_priorities,
            municipality=municipality, full_consent_bool=full_consent_bool,
            lite_mode=True, seed_base=seed_base,
            overcapacity_pct=OVERCAPACITY_PCT,
            demand_proportional_capacity=ADD_CAPACITIES_BY_DEMAND,
        )
        for algo, per_iter in per_algo_iters.items():
            for k in Run_School_Switch.k_intervals:
                # Mean / std across iterations for this (muni, algo, k).
                pct_switch_vals = [d[k]['percent_switchers']                       for d in per_iter]
                pct_first_vals  = [d[k]['percent_first_preference_switchers']       for d in per_iter]
                tot_stud_vals   = [d[k]['total_nr_students']                        for d in per_iter]
                rows.append({
                    'muni': municipality,
                    'algo': algo,
                    'k': k,
                    'overcapacity_pct': x_value,
                    'total_students_mean': statistics.mean(tot_stud_vals),
                    'pct_switchers_mean':  statistics.mean(pct_switch_vals),
                    'pct_switchers_std':   (statistics.stdev(pct_switch_vals) if len(pct_switch_vals) > 1 else 0.0),
                    'pct_first_pref_switchers_mean': statistics.mean(pct_first_vals),
                    'pct_first_pref_switchers_std':  (statistics.stdev(pct_first_vals) if len(pct_first_vals) > 1 else 0.0),
                })
    fieldnames = ['muni', 'algo', 'k', 'overcapacity_pct',
                  'total_students_mean',
                  'pct_switchers_mean', 'pct_switchers_std',
                  'pct_first_pref_switchers_mean', 'pct_first_pref_switchers_std']
    with open(out_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"[lite] wrote {out_path} ({len(rows)} rows)")


if lite_mode:
    _run_lite_mode()
else:
    for municipality in list_of_municipalities:
        Run_School_Switch().run_loop(n_iterations, test_mode, which_test_mode, unit_demand_mode, base_capacity, randomise_dates, random_priorities, seed_base=seed_base, municipality=municipality, full_consent_bool=full_consent_bool, overcapacity_pct=OVERCAPACITY_PCT, demand_proportional_capacity=ADD_CAPACITIES_BY_DEMAND)
    Helper().summarise_across_municipalities(list_of_municipalities)