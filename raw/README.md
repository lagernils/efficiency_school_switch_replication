# `raw/` — input data

This directory is where both implementations read their input from. **It is
empty in this repository**, and the real data is not distributed with it.

## Data availability statement

The analysis uses school-switch administrative records from six Swedish
municipalities (Linköping, Malmö, Nacka, Norrköping, Uppsala and Växjö) for the
academic years 2020–2026. The records are individual-level: each row identifies
a pupil, the school they currently attend, and the schools they have applied to
switch to.

These are personal data concerning minors and **cannot be redistributed by the
authors**. They were obtained through a software provider that operates school
choice and school switch programs for Swedish municipalities, and remain the
property of the individual municipalities. Researchers seeking access should
contact the corresponding author (`nils.lager@hhs.se`), who can describe the
approvals and agreements each municipality requires. The authors cannot
guarantee that access will be granted.

Everything needed to reproduce the analysis *given* the data is in this
repository: both implementations, the analysis scripts, and the exact
configuration used.

## What you can run instead

`tools/make_synthetic_data.py` writes a synthetic dataset into this directory
with the same folder layout, filenames and column schema that the pipeline
expects, so the whole pipeline runs end to end without any real data:

```bash
python3 tools/make_synthetic_data.py
```

**The synthetic data is not a statistical reconstruction of the real data.**
Every parameter is stipulated by hand rather than estimated from the real
records — the only inputs taken from the real world are the six municipality
names and their academic-year spans, both of which are published in the paper.
Results computed on it will not reproduce the paper and should not be
interpreted. The generator documents each parameter at the top of the file.

Output is deterministic: the same `--seed` gives byte-identical files.

## Expected layout

Each municipality is a sub-directory holding the CSVs named in
`build/code/functions/get_data_impl/` (`original`) and
`build/code/functions/data_loading.py` (`replication_rr`):

```
raw/
├── Linköping/          2.1.1 Rundor.csv
├── Malmö/              2.1.2 PlacementRoundPeriod.csv
├── Nacka/              2.2 Participant.csv
├── Norrköping/         2.3 Chooseables.csv
├── Uppsala/            2.4 Participant-PriorityGround - Round <id>.csv
└── Växjö/
```

## Your own data

To run on your own extracts, keep them outside the repository and point
`SCHOOL_SWITCH_RAW_DIR` at the directory that holds the municipality folders.
Records that need to be skipped or rewritten go in the exception tables in
`exclusions/`. The main README explains both, under "Using your own data".

The hand-built test fixtures do not live here; they are in `tests/fixtures/`.
