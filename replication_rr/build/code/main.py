"""
Entry point for the simulation. Run directly:

    python3 build/code/main.py

Produces per-municipality CSVs under build/output/loop_results/ and then
aggregates to summary_stats_{DA|TTC}_ALL.csv.
"""

import sys
from pathlib import Path

# Make the `functions` package importable when run as `python3 main.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from functions.run_school_switch import Run_School_Switch
from functions.helper import Helper


# ---- Configuration (see README.md) ---------------------------
test_mode = False
which_test_mode = 'basic'            # 'basic' or 'nonmonotone' or 'blockingpair'
unit_demand_mode = False
randomise_dates = True if not test_mode else False
base_capacity = 0                     # (see README.md)
random_priorities = True              # STB on lottery number only
n_iterations = 3                      # Monte Carlo draws
full_consent_bool = True              # True => all students consent (EADAM = StuOLA);
                                      # False => no students consent (EADAM = DA)

# How much extra capacity to add, and how to spread it.
#
# OVERCAPACITY_PCT is the number of additional empty seats, expressed as a
# percentage of the active students in each (year, grade) market -- exactly the
# quantity on the x-axis of the capacity figure. In each market the budget is
# round(OVERCAPACITY_PCT / 100 * n_students), handed out across the programs
# that appear in at least one rank-ordered list, using largest-remainder
# rounding so the total is hit exactly.
#
# Leave it as None to fall back on the old `base_capacity` rule (the same
# integer number of seats at every school), which is what the paper's baseline
# and the k-sensitivity results use. masterfile.py's overcapacity loop sets it
# to 0, 10, 20, ... 100 in turn.
#
# ADD_CAPACITIES_BY_DEMAND selects how that budget is spread: False splits it
# evenly across programs, True splits it in proportion to how many students
# rank each program. See functions/dynamic.py:allocate_extra_seats.
OVERCAPACITY_PCT = None
ADD_CAPACITIES_BY_DEMAND = False

list_of_municipalities = ['Linköping', 'Malmö', 'Nacka',
                           'Norrköping', 'Uppsala', 'Växjö']


# If invoked via ../../../../masterfile.py, override the defaults above from the env var.
import json as _json, os as _os
_override = _json.loads(_os.environ.get('SCHOOL_SWITCH_CONFIG_JSON', '{}'))
for _k, _v in _override.items():
    if _k in globals():
        globals()[_k] = _v
if 'seed_base' in _override:     # module-level constant in functions/config.py
    from functions import config as _cfg_mod
    _cfg_mod.SEED_BASE = int(_override['seed_base'])
if 'k_intervals' in _override:   # module-level global in functions/run_school_switch.py
    from functions import run_school_switch as _rss
    _rss.K_INTERVALS = list(_override['k_intervals'])

# Lite-mode flag (set by masterfile when running the basecapacity loop). When
# True, run_loop returns the per-algo summarised DataFrames instead of writing
# per-muni CSVs, and `Helper.summarise_across_municipalities` is skipped.
lite_mode = bool(_override.get('lite_mode', False))


# ---- Run --------------------------------------------------------------------
def _run_lite_mode():
    """Overcapacity-loop output path: write a single combined CSV with one row
    per (muni, algo) at every k, plus an `overcapacity_pct` column. masterfile
    reads this file across overcapacity values and builds the aggregate table.

    Routed to build/output/overcapacity/ (even split) or
    build/output/overcapacity_demandprop/ (ADD_CAPACITIES_BY_DEMAND=True) so
    the two counterfactuals' cached CSVs never collide."""
    import csv as _csv
    from functions import config as _cfg
    from functions import run_school_switch as _rss

    subfolder = "overcapacity_demandprop" if ADD_CAPACITIES_BY_DEMAND else "overcapacity"
    out_dir = _cfg.OUTPUT_DIR.parent / subfolder
    out_dir.mkdir(parents=True, exist_ok=True)
    x_value = 0 if OVERCAPACITY_PCT is None else OVERCAPACITY_PCT
    out_path = out_dir / f"run_x{x_value:g}.csv"

    rows = []
    for municipality in list_of_municipalities:
        per_algo = Run_School_Switch().run_loop(
            n_iterations, test_mode, which_test_mode, unit_demand_mode,
            base_capacity, randomise_dates, random_priorities,
            municipality=municipality,
            full_consent_bool=full_consent_bool,
            lite_mode=True,
            overcapacity_pct=OVERCAPACITY_PCT,
            demand_proportional_capacity=ADD_CAPACITIES_BY_DEMAND,
        )
        if per_algo is None:
            continue
        for algo, df in per_algo.items():
            for _, r in df.iterrows():
                rows.append({
                    'muni': municipality,
                    'algo': algo,
                    'k': int(r['k']),
                    'overcapacity_pct': x_value,
                    'total_students_mean':         r['total_students_mean'],
                    'pct_switchers_mean':          r['pct_switchers_mean'],
                    'pct_switchers_std':           r['pct_switchers_std'],
                    'pct_first_pref_switchers_mean': r['pct_first_pref_switchers_mean'],
                    'pct_first_pref_switchers_std':  r['pct_first_pref_switchers_std'],
                })
    fieldnames = ['muni', 'algo', 'k', 'overcapacity_pct',
                  'total_students_mean',
                  'pct_switchers_mean', 'pct_switchers_std',
                  'pct_first_pref_switchers_mean', 'pct_first_pref_switchers_std']
    with open(out_path, 'w', newline='') as f:
        w = _csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"[lite] wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    if lite_mode:
        _run_lite_mode()
    else:
        for municipality in list_of_municipalities:
            Run_School_Switch().run_loop(
                n_iterations, test_mode, which_test_mode, unit_demand_mode,
                base_capacity, randomise_dates, random_priorities,
                municipality=municipality,
                full_consent_bool=full_consent_bool,
                overcapacity_pct=OVERCAPACITY_PCT,
                demand_proportional_capacity=ADD_CAPACITIES_BY_DEMAND,
            )
        Helper().summarise_across_municipalities(list_of_municipalities)
