"""Top-level runner for the two code projects (original / replication_rr).

Edit the settings below, then run:

    python3 masterfile.py

There are two run modes:

  (1) STANDARD MODE (run_loop_over_basecapacity_bool = False)
      For each enabled project: python main.py, then Rscript run_analysis.R.
      Produces the paper's headline results -- Table 1 and the k-sensitivity
      figure -- under <project>/analysis/output/.

  (2) CAPACITY-LOOP MODE (run_loop_over_basecapacity_bool = True)
      For each enabled project: python main.py is run once per value in
      `overcapacity_values` (additional seats as a percentage of active
      students), at a single fixed k. Produces the capacity counterfactual --
      the paper's Figure 2 -- under
      <project>/analysis/output/sum_overcapacity/.

      NOTE this is the slower of the two modes by a wide margin: 21 capacity
      values x `n_iterations` draws x 6 municipalities. Reduce n_iterations
      for a smoke test.

Both main.py files stay runnable on their own with their hardcoded defaults;
when masterfile is used, settings below are pushed in via a JSON env var.
"""

import json
import os
import shutil
import subprocess
import sys
import csv
from pathlib import Path


# === Standard-mode settings (used when run_loop_over_basecapacity_bool=False)
test_mode              = False
which_test_mode        = 'basic'             # 'basic' | 'nonmonotone' | 'blockingpair'
unit_demand_mode       = False
randomise_dates        = True if not test_mode else False
base_capacity          = 0
random_priorities      = True
n_iterations           = 250
# Monte Carlo seed base. Iteration i of a run uses seed_base + i, in BOTH
# implementations, so a run is reproducible and the knob lives in one place.
#
# Both implementations derive each student's lottery number from
# (seed, participantId) rather than from position in a draw sequence, so an
# equal seed_base gives them IDENTICAL lotteries and they can be compared
# draw-for-draw (verified: 750 of 750 match on one test market).
seed_base              = 424242
full_consent_bool      = True                # False => EADAM == DA (robustness check)
ADD_CAPACITIES_BY_DEMAND = False             # supported by both implementations
k_intervals            = [10, 30, 60, 90, 120, 180, 365]            # placement-round spacing in days
list_of_municipalities = ['Linköping', 'Malmö', 'Nacka',
                          'Norrköping', 'Uppsala', 'Växjö']
standard_target        = 'replication_rr'              # 'original' | 'replication_rr' | 'all'


# === Capacity-loop settings =================================================
# When True, masterfile skips the standard pipeline and instead runs a loop
# over capacity values at a single k, producing a single LaTeX table per
# project under <project>/analysis/output/.
run_loop_over_basecapacity_bool = False
loop_fixed_k                    = 90
loop_target                     = 'replication_rr'   # 'original' | 'replication_rr' | 'all'

# The loop is parameterised in one of two ways, depending on the target.
#
#   'original' and 'replication_rr' loop over `overcapacity_values`: additional empty seats
#   as a PERCENTAGE OF ACTIVE STUDENTS in each (year, grade) market -- exactly
#   the quantity plotted on the figure's x-axis. This is what lets the grid be
#   0, 10, 20, ... rather than the ~33-point steps forced by adding whole seats
#   at every program. Output goes to build/output/overcapacity[_demandprop]/.
#
#   'replication' loops over `base_capacity_values`: a whole number of extra
#   seats at every school. That project has not been updated for the percentage
#   parameterisation, so it keeps the old path and writes to
#   build/output/basecapacity/ as before. (It is not shipped in this package.)
overcapacity_values             = list(range(0, 101, 5))   # 0, 5, 10, ... 100
# Retained only for the legacy whole-seats parameterisation. Neither project
# shipped in this package uses it (see _uses_overcapacity below), so changing
# it has no effect; it is kept so the legacy code path stays runnable if this
# masterfile is ever pointed at an older codebase.
base_capacity_values            = [0,1,2,3,4,5,6,7,8,9,10]

# The overcapacity figure is rendered twice from the same runs: once over the
# full 0-100% range, and once zoomed to 0-50% where the efficiency gap actually
# closes. See run_plot_basecapacity.R.
overcapacity_plot_ranges        = {'full': 100, 'zoom': 50}


def _uses_overcapacity(project: dict) -> bool:
    """True for the project(s) that take overcapacity_pct rather than an
    integer base_capacity. Kept as a helper so adding another updated project
    later is a one-line change."""
    return project['name'] in ('original', 'replication_rr')


# === Projects this masterfile drives ========================================
ROOT = Path(__file__).resolve().parent
PROJECTS = [
    {
        'name':    'original',
        'py_cwd':  ROOT / 'original' / 'build' / 'code',
        'r_cwd':   ROOT / 'original',
        'r_script': ROOT / 'original' / 'analysis' / 'code' / 'run_analysis.R',
        'r_plot_basecapacity':  ROOT / 'original' / 'analysis' / 'code' / 'run_plot_basecapacity.R',
        'r_plot_k_sensitivity': ROOT / 'original' / 'analysis' / 'code' / 'run_plot_k_sensitivity.R',
    },
    {
        'name':    'replication_rr',
        'py_cwd':  ROOT / 'replication_rr' / 'build' / 'code',
        'r_cwd':   ROOT / 'replication_rr',
        'r_script': ROOT / 'replication_rr' / 'analysis' / 'code' / 'run_analysis.R',
        'r_plot_basecapacity':  ROOT / 'replication_rr' / 'analysis' / 'code' / 'run_plot_basecapacity.R',
        'r_plot_k_sensitivity': ROOT / 'replication_rr' / 'analysis' / 'code' / 'run_plot_k_sensitivity.R',
    },
]


def _projects_for(target: str) -> list:
    """Resolve target='original'|'replication_rr'|'all' into a list of project dicts."""
    if target == 'all':
        return list(PROJECTS)
    return [p for p in PROJECTS if p['name'] == target]


def _basecap_subdir(project: dict | None = None) -> str:
    """Evenly-split vs demand-proportional runs are cached in separate
    subfolders so neither overwrites the other's run CSVs/diagnostic data.
    Updated projects use overcapacity*/ and run_x<N>.csv; the older ones keep
    basecapacity*/ and run_p<N>.csv."""
    stem = 'overcapacity' if (project and _uses_overcapacity(project)) else 'basecapacity'
    return f'{stem}_demandprop' if ADD_CAPACITIES_BY_DEMAND else stem


def _fname_suffix() -> str:
    """Output filename/label suffix, mirroring run_plot_basecapacity.R's
    fname_suffix so uniform vs demand-proportional outputs never collide."""
    return '_demandprop' if ADD_CAPACITIES_BY_DEMAND else '_uniform'


def _config_env(overrides: dict | None = None) -> dict:
    """Build the env for subprocess calls, with our settings in one JSON blob.
    Pass `overrides` to replace a few config keys (used by the basecapacity loop)."""
    cfg = {
        'test_mode':              test_mode,
        'which_test_mode':        which_test_mode,
        'unit_demand_mode':       unit_demand_mode,
        'randomise_dates':        randomise_dates,
        'base_capacity':          base_capacity,
        'random_priorities':      random_priorities,
        'n_iterations':           n_iterations,
        'full_consent_bool':      full_consent_bool,
        'k_intervals':            k_intervals,
        'list_of_municipalities': list_of_municipalities,
        'ADD_CAPACITIES_BY_DEMAND': ADD_CAPACITIES_BY_DEMAND,
        'seed_base':              seed_base,
    }
    if overrides:
        cfg.update(overrides)
    return {**os.environ, 'SCHOOL_SWITCH_CONFIG_JSON': json.dumps(cfg)}


def _run_python(project: dict, env: dict) -> None:
    print(f'\n--- [{project["name"]}] python main.py ---')
    subprocess.run([sys.executable, 'main.py'],
                   cwd=str(project['py_cwd']), env=env, check=True)


def _run_r(project: dict) -> None:
    rscript = shutil.which('Rscript')
    if rscript is None:
        print(f'--- [{project["name"]}] skipping R: Rscript not found on PATH ---')
        return
    if not project['r_script'].exists():
        print(f'--- [{project["name"]}] skipping R: {project["r_script"].name} not found ---')
        return
    print(f'\n--- [{project["name"]}] Rscript {project["r_script"].name} ---')
    subprocess.run([rscript, str(project['r_script'])],
                   cwd=str(project['r_cwd']), check=True)


def _run_r_script(project: dict, key: str) -> None:
    """Run a named auxiliary R script (e.g. 'r_plot_basecapacity') for one project.
    Skips silently if Rscript or the script is missing, mirroring `_run_r`."""
    rscript = shutil.which('Rscript')
    script = project.get(key)
    if rscript is None:
        print(f'--- [{project["name"]}] skipping {key}: Rscript not found on PATH ---')
        return
    if script is None or not script.exists():
        name = script.name if script is not None else key
        print(f'--- [{project["name"]}] skipping {key}: {name} not found ---')
        return
    print(f'\n--- [{project["name"]}] Rscript {script.name} ---')
    subprocess.run([rscript, str(script)],
                   cwd=str(project['r_cwd']), check=True)


def _write_plot_meta(project: dict) -> None:
    """Write build/output/plot_meta_basecapacity.json for the R plot script.
    Deliberately lives one level above the basecapacity/basecapacity_demandprop
    subfolders (rather than inside either) so the R script can read it -- and
    learn which subfolder to read next -- before it has picked a subfolder.
    Captures the run-context the caption needs (k, n_iterations, munis,
    priority scheme, EADAM consent setting, base_capacity range, and the
    capacity-allocation mode, which the R script uses to pick both its
    input subfolder and its output filename suffix)."""
    out_path = project['py_cwd'].parent / 'output' / 'plot_meta_basecapacity.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        'project':                  project['name'],
        'loop_fixed_k':             loop_fixed_k,
        'n_iterations':             n_iterations,
        'base_capacity_values':     list(base_capacity_values),
        'list_of_municipalities':   list(list_of_municipalities),
        'random_priorities':        random_priorities,
        'full_consent_bool':        full_consent_bool,
        'randomise_dates':          randomise_dates,
        'ADD_CAPACITIES_BY_DEMAND': ADD_CAPACITIES_BY_DEMAND,
        # Overcapacity parameterisation (replication_rr). `uses_overcapacity`
        # tells the R script to read overcapacity*/run_x<N>.csv on a true
        # percentage x-axis instead of basecapacity*/run_p<N>.csv on discrete
        # tick positions; `overcapacity_plot_ranges` gives the x-axis upper
        # bound for each figure variant it should render.
        'uses_overcapacity':          _uses_overcapacity(project),
        'overcapacity_values':        list(overcapacity_values),
        'overcapacity_plot_ranges':   dict(overcapacity_plot_ranges),
    }
    with open(out_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f'  wrote {out_path}')


def _write_plot_meta_standard(project: dict) -> None:
    """Write build/output/plot_meta.json for the standard-mode R plot scripts
    (k-sensitivity figure etc.). Captures the same run-context as the
    basecapacity loop's meta, minus the loop-specific fields."""
    out_path = project['py_cwd'].parent / 'output' / 'plot_meta.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        'project':                project['name'],
        'k_intervals':            list(k_intervals),
        'n_iterations':           n_iterations,
        'base_capacity':          base_capacity,
        'list_of_municipalities': list(list_of_municipalities),
        'random_priorities':      random_priorities,
        'full_consent_bool':      full_consent_bool,
        'randomise_dates':        randomise_dates,
    }
    with open(out_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f'  wrote {out_path}')


# =============================================================================
# Standard mode
# =============================================================================
def run_standard() -> None:
    targets = _projects_for(standard_target)
    if not targets:
        sys.exit(f"Unknown standard_target {standard_target!r}; expected "
                 "'original', 'replication_rr' or 'all'.")
    env = _config_env()
    for project in targets:
        _run_python(project, env)
        _write_plot_meta_standard(project)
        _run_r(project)  # run_analysis.R orchestrates make_tables.R + plots
    print('\nAll done. Outputs:')
    for project in targets:
        print(f'  {project["name"]}: CSVs in {project["py_cwd"].parent / "output" / "loop_results"}')
        print(f'  {project["name"]}: tables in {project["r_cwd"] / "analysis" / "output"}')


# =============================================================================
# Base-capacity-loop mode
# =============================================================================
def _read_run_csv(project: dict, p) -> list:
    """Read the lite-mode combined CSV emitted by main.py for one loop value.
    Schema: muni, algo, k, {overcapacity_pct|base_capacity}, total_students_mean,
    pct_switchers_mean/std, pct_first_pref_switchers_mean/std."""
    fname = f'run_x{p:g}.csv' if _uses_overcapacity(project) else f'run_p{p}.csv'
    path = project['py_cwd'].parent / 'output' / _basecap_subdir(project) / fname
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def _aggregate_across_munis(rows: list, algo: str) -> dict:
    """Applicant-weighted aggregate of the lite-mode rows for a given algo at
    k == loop_fixed_k."""
    sub = [r for r in rows if r['algo'] == algo
           and int(float(r['k'])) == loop_fixed_k]
    if not sub:
        return None
    weights = [float(r['total_students_mean']) for r in sub]
    N = sum(weights)
    if N == 0:
        return None
    pct_switch = sum(w * float(r['pct_switchers_mean']) for w, r in zip(weights, sub)) / N
    pct_first  = sum(w * float(r['pct_first_pref_switchers_mean']) for w, r in zip(weights, sub)) / N

    def lotv(col_mean: str, col_std: str, grand: float) -> float:
        within  = sum(w * float(r[col_std])**2 for w, r in zip(weights, sub)) / N
        between = sum(w * (float(r[col_mean]) - grand)**2 for w, r in zip(weights, sub)) / N
        return (within + between) ** 0.5
    return {
        'pct_switch_mean': pct_switch,
        'pct_switch_std':  lotv('pct_switchers_mean', 'pct_switchers_std', pct_switch),
        'pct_first_mean':  pct_first,
        'pct_first_std':   lotv('pct_first_pref_switchers_mean', 'pct_first_pref_switchers_std', pct_first),
        'total_students':  N,
    }


def _read_unique_programs(project: dict) -> list:
    """Read build/output/basecapacity/diagnostic_unique_programs.csv (rows: muni,
    year, grade, n_students, n_unique_programs). Returns list of dicts with
    float values."""
    path = project['py_cwd'].parent / 'output' / _basecap_subdir(project) / 'diagnostic_unique_programs.csv'
    if not path.exists():
        return []
    with open(path) as f:
        return [
            {**r,
             'n_students': float(r['n_students']),
             'n_unique_programs': float(r['n_unique_programs'])}
            for r in csv.DictReader(f)
        ]


def _pct_overcap(diagnostic: list, p, project: dict | None = None) -> float:
    """Additional seats as a percentage of active students.

    For projects on the overcapacity parameterisation this is just the loop
    value itself -- that is the whole point of the change: the knob we turn and
    the axis we plot are now the same number, so no conversion is needed.

    For the legacy base_capacity projects it is the applicant-weighted average
    over (year, grade) markets of
        pct_overcap_market = (n_unique_programs * p) / n_students * 100
    which reduces to sum(n_unique_programs * p * 100) / sum(n_students).
    """
    if project is not None and _uses_overcapacity(project):
        return float(p)
    if not diagnostic:
        return 0.0
    total_extra = sum(d['n_unique_programs'] for d in diagnostic) * p * 100
    total_stud  = sum(d['n_students'] for d in diagnostic)
    return total_extra / total_stud if total_stud > 0 else 0.0


def _write_basecapacity_table(project: dict, results: dict) -> None:
    """results: dict keyed by the loop value, with sub-dicts per algo + 'pct_overcap'.

    On the overcapacity parameterisation the loop value *is* the percentage of
    additional seats, so the old two-column "base capacity / % overcap" header
    collapses into a single column."""
    overcap_mode = _uses_overcapacity(project)
    stem = 'overcapacity' if overcap_mode else 'basecapacity'
    out_dir = project['r_cwd'] / 'analysis' / 'output' / f'sum_{stem}'
    out_dir.mkdir(parents=True, exist_ok=True)
    outpath = out_dir / f'output_{stem}{_fname_suffix()}.tex'

    fmt_v = lambda x: f'{x:.2f}'
    fmt_s = lambda x: f'({x:.2f})'

    if overcap_mode:
        colspec  = r'\begin{tabular}{l ccc | ccc}'
        header   = [
            r'\textbf{\% Extra seats}',
            r'  & \multicolumn{3}{c|}{\textbf{\% Switchers}}',
            r'  & \multicolumn{3}{c}{\textbf{\% Assigned to First Choice}} \\',
            r'\cmidrule(lr){2-4}\cmidrule(lr){5-7}',
            r'  & \underline{DA} & \underline{EADAM} & \underline{TTC}',
            r'  & \underline{DA} & \underline{EADAM} & \underline{TTC} \\',
        ]
        lead     = lambda p, r: f'{p:g}'
        std_lead = r' '
        allocation = ('in proportion to the number of students ranking each program'
                      if ADD_CAPACITIES_BY_DEMAND else 'evenly across programs')
        caption = (rf'\caption{{Outcomes by additional capacity (k = {loop_fixed_k} days, '
                   rf'{n_iterations} lottery draws). \% Extra seats is the number of '
                   r'additional empty seats as a percentage of active students in each '
                   rf'(year, grade) market, allocated {allocation}. '
                   r'Applicant-weighted standard deviations across lottery draws and '
                   r'municipalities in parentheses.}')
    else:
        colspec  = r'\begin{tabular}{l l ccc | ccc}'
        header   = [
            r'\textbf{Base capacity} & \textbf{\% Overcap}',
            r'  & \multicolumn{3}{c|}{\textbf{\% Switchers}}',
            r'  & \multicolumn{3}{c}{\textbf{\% Assigned to First Choice}} \\',
            r'\cmidrule(lr){3-5}\cmidrule(lr){6-8}',
            r'  & & \underline{DA} & \underline{EADAM} & \underline{TTC}',
            r'  & \underline{DA} & \underline{EADAM} & \underline{TTC} \\',
        ]
        lead     = lambda p, r: f'{p}  & {fmt_v(r["pct_overcap"])} '
        std_lead = r' & '
        caption = (rf'\caption{{Outcomes by base capacity (k = {loop_fixed_k} days, '
                   rf'{n_iterations} lottery draws). '
                   r'\% Overcapacity is the applicant-weighted average over (year, grade) '
                   r'markets of (unique programs ranked $\times$ base capacity) / students. '
                   r'Applicant-weighted standard deviations across lottery draws and '
                   r'municipalities in parentheses.}')

    lines = [
        r'\begin{table}[htbp]',
        r'\centering',
        r'\small',
        colspec,
        r'\toprule',
        *header,
        r'\midrule',
    ]
    p_keys = sorted(results.keys())
    for i, p in enumerate(p_keys):
        r = results[p]
        sep = r' \\[4pt]' if i < len(p_keys) - 1 else r' \\'
        # value row
        lines.append(
            f'{lead(p, r)}'
            f' & {fmt_v(r["DA"]["pct_switch_mean"])}  & {fmt_v(r["EADAM"]["pct_switch_mean"])}  & {fmt_v(r["TTC"]["pct_switch_mean"])}'
            f'  & {fmt_v(r["DA"]["pct_first_mean"])}   & {fmt_v(r["EADAM"]["pct_first_mean"])}   & {fmt_v(r["TTC"]["pct_first_mean"])}'
            r'  \\'
        )
        # std row
        lines.append(
            std_lead
            + f'  & {fmt_s(r["DA"]["pct_switch_std"])} & {fmt_s(r["EADAM"]["pct_switch_std"])} & {fmt_s(r["TTC"]["pct_switch_std"])}'
            + f'  & {fmt_s(r["DA"]["pct_first_std"])}  & {fmt_s(r["EADAM"]["pct_first_std"])}  & {fmt_s(r["TTC"]["pct_first_std"])}'
            + f'{sep}'
        )
    lines += [
        r'\bottomrule',
        r'\end{tabular}',
        caption,
        rf'\label{{tab:{stem}{_fname_suffix()}}}',
        r'\end{table}',
    ]
    with open(outpath, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'  wrote {outpath}')


def run_basecapacity_loop() -> None:
    print(f'\n=== capacity-loop mode ===')
    print(f'  k = {loop_fixed_k}, n_iterations = {n_iterations}, target = {loop_target}')
    targets = _projects_for(loop_target)
    if not targets:
        sys.exit(f'Unknown loop_target {loop_target!r}; expected '
                 "'original', 'replication_rr' or 'all'.")

    for project in targets:
        overcap_mode = _uses_overcapacity(project)
        loop_values = overcapacity_values if overcap_mode else base_capacity_values
        label = 'overcapacity_pct' if overcap_mode else 'base_capacity'
        print(f'  [{project["name"]}] {label} values = {loop_values}')
        results = {}
        diagnostic = None
        for p in loop_values:
            print(f'\n--- [{project["name"]}] {label} = {p} ---')
            env = _config_env({
                'OVERCAPACITY_PCT': p if overcap_mode else None,
                'base_capacity':    0 if overcap_mode else p,
                'k_intervals':      [loop_fixed_k],
                'lite_mode':        True,
            })
            _run_python(project, env)

            if diagnostic is None:
                diagnostic = _read_unique_programs(project)
                if not diagnostic:
                    print(f'  WARNING: diagnostic_unique_programs.csv not found '
                          f'in {project["py_cwd"].parent / "output" / _basecap_subdir(project)} — '
                          f'pct_overcap will be 0.')

            run_rows = _read_run_csv(project, p)
            row = {'pct_overcap': _pct_overcap(diagnostic, p, project)}
            for algo in ('DA', 'EADAM', 'TTC'):
                agg = _aggregate_across_munis(run_rows, algo)
                if agg is None:
                    print(f'  WARNING: no rows for {algo} at k={loop_fixed_k}')
                    row[algo] = {'pct_switch_mean': 0, 'pct_switch_std': 0,
                                 'pct_first_mean': 0,  'pct_first_std': 0}
                else:
                    row[algo] = agg
            results[p] = row

        _write_basecapacity_table(project, results)
        _write_plot_meta(project)
        _run_r(project)  # run_analysis.R skips tables/k-sens cleanly, runs basecapacity plot

    print('\nAll done.')


# =============================================================================
# Entry point
# =============================================================================
def main() -> None:
    if run_loop_over_basecapacity_bool:
        run_basecapacity_loop()
    else:
        run_standard()


if __name__ == '__main__':
    main()
