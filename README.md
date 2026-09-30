# Unlocking Legal Efficiency Gains in School Switch Programs — replication package

Replication code for Andersson, Lager and Kessel, *Unlocking Legal Efficiency
Gains in School Switch Programs*, **Economics Letters**.

The paper compares Deferred Acceptance (DA) against Top Trading Cycles (TTC) and
Efficiency-Adjusted Deferred Acceptance (EADAM) in Swedish school *switch*
programs, where every participant already holds a seat, and asks how the
efficiency gap between the stable and the efficient mechanisms responds to
adding spare capacity.

**No real data is distributed with this package.** The municipality extracts are
individual-level administrative records for school pupils and cannot be
redistributed; see the data availability statement in
[`raw/README.md`](raw/README.md). You can run everything in two ways:

- **with synthetic data** that the package generates for you — see
  [Quick start](#quick-start-synthetic-data); or
- **with your own data** in the same format — see
  [Using your own data](#using-your-own-data).

---

## Two implementations, on purpose

This package ships **two independent implementations of the same design**.

| | `original/` | `replication_rr/` |
|---|---|---|
| Written by | the authors | an LLM, by pair-programming |
| Written from | — | a written description of what `original` does, with no sight of how it does it |
| Speed | slow | roughly 5× faster |
| Checks | verifies optimal stability every DA round | no in-loop verification |
| Use it for | the authoritative account of the design | extending the analysis, or replicating on other data |

They were developed independently and agree. Publishing both is the point: the
results do not rest on one codebase, and the second is a practical starting
point for anyone applying this design to different data, due to its superior speed.

---

## Requirements

**Python 3.10+** with `pandas` and `numpy`.

**R 4.x** with `dplyr`, `tidyr`, `readr`, `ggplot2`, `glue`, `purrr`.
Optional but recommended: `ragg` and `systemfonts` (for PNG rendering and Times
New Roman); `showtext` and `sysfonts` as a font fallback. Missing optional
packages degrade gracefully with a message.

Also install `jsonlite` and `patchwork`. `patchwork` is required for the
k-sensitivity figure. Without `jsonlite` the capacity-figure script cannot read
`build/output/plot_meta_basecapacity.json` and silently falls back to defaults
for the allocation mode and axis range — i.e. it can render the wrong figure
variant without complaining. Install both.

```bash
pip install -r requirements.txt
```

```r
install.packages(c("dplyr","tidyr","readr","ggplot2","glue","jsonlite",
                   "patchwork","purrr","ragg","systemfonts"))
```

---

## Quick start (synthetic data)

```bash
python3 tools/make_synthetic_data.py     # writes a synthetic dataset into raw/
python3 masterfile.py                    # simulation, then tables and figures
```

`make_synthetic_data.py` writes fabricated data into `raw/` for the six
municipalities, with the same folder layout, filenames, columns and value
conventions as the real extracts. `masterfile.py` then runs the simulation for
`replication_rr` and the R analysis, and writes Table 1 and the k-sensitivity
figure to `replication_rr/analysis/output/`.

**The synthetic data is not a statistical reconstruction of the real data.**
Every parameter is stipulated by hand and nothing is estimated from the real
extracts, so the numbers you get will not match the paper and carry no
substantive meaning. The point is to show that the pipeline runs end to end and
what the input has to look like. The generator documents each parameter at the
top of the file, and the same `--seed` always gives byte-identical files.

For a fast first run, open `masterfile.py` and set `n_iterations` to something
small (2 is plenty) before running it. At the paper's 250 draws a full run of
`replication_rr` takes a while; `original` is considerably slower.

---

## Tests

`tests/fixtures/` holds three tiny hand-built switching markets (4 to 10 pupils,
schools "School A" to "School D"), small enough to check by hand:

| Fixture | `which_test_mode` | Pupils | Rounds |
|---|---|---|---|
| `Test/` | `basic` | 10 | 3 |
| `Test_NonMonotone/` | `nonmonotone` | 6 | 3 |
| `Test_BlockingPair/` | `blockingpair` | 4 | 1 |

Run both implementations on all three with one command:

```bash
python3 tests/run_tests.py
```

It checks that `original` and `replication_rr` both run cleanly on each fixture,
and compares the number of switchers `replication_rr` reports under DA, TTC and
EADAM with values recorded from this version of the code. A mismatch means
behaviour has changed — useful if you modify the algorithms. It needs no data in
`raw/` and takes a few seconds. It writes to the same `build/output/` folders as a
normal run, so run it before, not after, a run whose output you want to keep.

To follow one example round by round, run `original` directly in test mode. It
prints every round's placements, each school's admitted pupils and the
capacity checks to the console:

```bash
cd original/build/code
SCHOOL_SWITCH_CONFIG_JSON='{"test_mode": true, "which_test_mode": "basic", "n_iterations": 1, "randomise_dates": false, "list_of_municipalities": ["Växjö"]}' python3 main.py
```

(The municipality name is only a label in test mode; the fixture is read
regardless.)

---

## Using your own data

### Format

Your data must follow the layout the synthetic generator writes — one folder per
municipality, five kinds of CSV:

```
<your raw dir>/
└── <Municipality>/
    ├── 2.1.1 Rundor.csv                                  placement rounds
    ├── 2.1.2 PlacementRoundPeriod.csv                    application windows
    ├── 2.2 Participant.csv                               participants, current school
    ├── 2.3 Chooseables.csv                               school programmes, capacities
    └── 2.4 Participant-PriorityGround - Round <id>.csv   rank-ordered lists, one file per round
```

The easiest way to get the columns and value conventions right is to generate
the synthetic dataset and use it as a template: every file, column and id
convention the loaders depend on is present there, and
`tools/make_synthetic_data.py` explains each one in its docstring. Dates are ISO
(`YYYY-MM-DD`, optionally followed by a time).

Municipality names and academic years are set in a few places, which you need
to edit if yours differ from the paper's six:

- `list_of_municipalities` in `masterfile.py` — which municipalities to run;
- `ACADEMIC_YEARS` in `replication_rr/build/code/functions/config.py` and
  `Helper.get_years` in `original/build/code/functions/main_helper.py` — the
  academic years per municipality;
- `municipalities` and the year-range labels near the top of
  `<project>/analysis/code/make_tables.R` — the rows of Table 1.

### Pointing the code at your data

Keep your data outside this repository and point `SCHOOL_SWITCH_RAW_DIR` at it:

```bash
export SCHOOL_SWITCH_RAW_DIR=/path/to/your/raw
python3 masterfile.py
```

Both implementations honour the variable, so one setting moves both and they
are guaranteed byte-identical inputs. Unset it (or open a new terminal) to go
back to the synthetic data in `raw/`.

### Data-cleaning exceptions

Real extracts usually contain records that have to be skipped or rewritten
before the placement problem can be assembled. Four small lookup tables in
[`exclusions/`](exclusions/README.md) handle that:

| File | What it does |
|---|---|
| `excluded_rounds.csv` | placement rounds to drop (test rounds, rounds opened and never used) |
| `spgid_remap.csv` | old → new school-programme-grade id, for ids reissued mid-sample |
| `spid_alias.csv` | old → new school-programme id, same reason |
| `manual_grade_overrides.csv` | the grade to use for a participant who appears at several grades and cannot be resolved automatically |

They ship **header-only**: the synthetic data needs no exceptions. Put your own
values in a sibling file with `.local` before the extension —
`exclusions/excluded_rounds.local.csv` and so on. A `.local.csv` takes
precedence over the committed file and is gitignored, so identifiers from your
source system cannot reach a commit by accident. `exclusions/README.md`
documents the schemas.

If a participant appears at more than one grade and has no entry in
`manual_grade_overrides`, the two implementations react differently:
`original` stops with `ValueError: Cannot resolve grade for student <id>`, and
`replication_rr` drops that participant and continues.

---

## Running it

Everything is driven by `masterfile.py` at the repository root, which sets the
configuration, runs the Python simulation as a subprocess and then the R
analysis scripts. Edit the settings at the top of the file and run
`python3 masterfile.py`.

### The two modes

`masterfile.py` has one switch at the top:

```python
run_loop_over_basecapacity_bool = False   # main results (Table 1, Figure 1)
                                # True    # capacity counterfactual (Figure 2)
```

**Standard mode** (`False`, the default) produces the paper's main results:
per-municipality switching rates across run frequencies
`k_intervals = [10, 30, 60, 90, 120, 180, 365]`, written to
`<project>/build/output/loop_results/`, then aggregated into Table 1 and the
k-sensitivity figure under `<project>/analysis/output/`.

**Capacity-loop mode** (`True`) produces the capacity counterfactual: it fixes
`k = loop_fixed_k` and sweeps `overcapacity_values = 0, 5, 10, … 100`, the number
of additional empty seats as a percentage of active students in each
(year, grade) market. Output goes to
`<project>/build/output/overcapacity[_demandprop]/run_x<N>.csv` and then to
`<project>/analysis/output/sum_overcapacity/`. This is by far the slower mode:
21 capacity values × `n_iterations` draws × 6 municipalities.

`ADD_CAPACITIES_BY_DEMAND` selects how the seat budget is spread: `False` splits
it evenly across programmes, `True` in proportion to how many students rank each
programme. The two allocation modes write to separate folders, so neither
overwrites the other.

`standard_target` / `loop_target` choose which implementation to run:
`'original'`, `'replication_rr'` or `'all'`.

### Regenerating only the figures

The R plotting scripts read the cached run CSVs, so figures can be redrawn
without re-running the simulation:

```bash
cd replication_rr && Rscript analysis/code/run_plot_basecapacity.R
```

The script picks its allocation mode from
`build/output/plot_meta_basecapacity.json`, so a bare run regenerates whichever
mode was produced last.

### Runtime

The published results use `n_iterations = 250`. In standard mode that is a
substantial run for `replication_rr` and a much longer one for `original`; in
capacity-loop mode, hours for `replication_rr`. Reduce `n_iterations` for a
smoke test.

---

## Layout

```
├── masterfile.py                 driver: config, runs Python then R
├── raw/                          input data (gitignored; see README there)
├── exclusions/                   data-cleaning exceptions (header-only here)
├── tests/
│   ├── run_tests.py              runs both implementations on the fixtures
│   └── fixtures/                 three hand-built worked examples
├── tools/
│   └── make_synthetic_data.py    synthetic dataset generator
├── LICENSE  requirements.txt  r-requirements.txt
├── original/
│   ├── build/code/               simulation (main.py + functions/)
│   └── analysis/                 R scripts (output/ is generated, not committed)
└── replication_rr/
    ├── build/code/               simulation (main.py + functions/)
    └── analysis/                 R scripts (output/ is generated, not committed)
```

**No generated output is committed.** Both `analysis/output/` and
`build/output/` are empty in this repository: every table, figure and
intermediate CSV is produced by running the pipeline.

Running the pipeline writes:

| What | Where | Paper exhibit |
|---|---|---|
| Summary statistics by district, k=90 | `<project>/analysis/output/table1.tex` | **Table 1** |
| Outcomes by run frequency | `<project>/analysis/output/sum_k/plot_k_sensitivity.png` | **Figure 1** |
| Switching vs additional capacity | `<project>/analysis/output/sum_overcapacity/plot_overcapacity_uniform_zoom.png` | **Figure 2** |

The capacity loop additionally produces `_full` variants (x-axis to 100% rather
than 50%), `_demandprop` variants (seats allocated in proportion to demand
rather than evenly) and `_firstchoice_panel` variants (first-choice placements
alongside switching); those were produced for the referee response and are not
in the paper.

---

## Method, in brief

For each municipality, academic year and grade, the academic year (30 June to
29 June) is divided into consecutive `k`-day windows. Students enter in the
window containing their application date and remain active until matched.

Each window runs DA, TTC or EADAM over the active students. A school's effective
capacity is the number of active students currently attending it, adjusted for
students who have already left or arrived — so switches reallocate occupied
seats rather than fill vacancies. Each student's current school is appended to
the bottom of their list ("bounce-back"), guaranteeing individual rationality.
Priorities are a single tie-breaking lottery, except that a student always has
top priority at their own current school.

Submitted rank-ordered lists are held fixed across the counterfactuals. Application
dates are re-randomised within the year for each Monte Carlo draw, which
is what allows run frequencies the districts never actually used to be evaluated.

---

## Acknowledgements

The TTC implementation in `original/build/code/functions/TTC_impl/` began as an
adaptation of [Luke Carani's matching-algorithms](https://github.com/lwcarani/matching-algorithms),
with thanks. It has been modified substantially for the capacity-constrained
school-switch setting. Any remaining errors are our own.

## Citation

> Andersson, T., Lager, N., and Kessel, D. Unlocking Legal Efficiency Gains in
> School Switch Programs. *Economics Letters*.

## Contact

Nils Lager, Department of Economics, Stockholm School of Economics —
`nils.lager@hhs.se`
