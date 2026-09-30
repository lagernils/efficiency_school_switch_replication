# Data-cleaning exceptions

Four lookup tables that the loaders consult while reading the input data. They are
**configuration, not data**: each row names an administrative record in the
source system that has to be skipped or rewritten before the placement problem
can be assembled.

| File | What it does |
|---|---|
| `excluded_rounds.csv` | Placement rounds to drop. Test rounds, rounds that were opened and never used, and rounds belonging to a different placement process. |
| `spgid_remap.csv` | Old → new `schoolProgramGradeId`, for school programmes whose ids were reissued mid-sample. |
| `spid_alias.csv` | Old → new `schoolProgramId`, same reason. |
| `manual_grade_overrides.csv` | The grade to use for a participant who appears at more than one grade and cannot be resolved automatically from their current school. |

## The files here are empty on purpose

This repository ships them with a header row and nothing else, so anyone can
see the mechanism and see that **no exception is applied to the synthetic
dataset**. That is correct: the synthetic generator never produces a test round,
a reissued id or an ambiguous grade, so there is nothing to exclude or rewrite.

## Running against your own data

If your extract needs exceptions, put them in a sibling file with `.local`
before the extension:

```
exclusions/excluded_rounds.local.csv
exclusions/spgid_remap.local.csv
exclusions/spid_alias.local.csv
exclusions/manual_grade_overrides.local.csv
```

A `.local.csv` file takes precedence over the committed one, for that table
only. `.gitignore` excludes `exclusions/*.local.csv`, so real identifiers from
your source system cannot reach a commit by accident.

Both implementations read these same files, so `original` and `replication_rr`
cannot drift apart on which records they exclude.

## Schemas

```
excluded_rounds.csv   municipality,placementRoundId,note
spgid_remap.csv       municipality,old_spgid,new_spgid,note
spid_alias.csv        municipality,old_spid,new_spid,note
manual_grade_overrides.csv  municipality,participantId,grade,note
```

`municipality` must match the name of the municipality's input folder exactly. `note` is free
text and is never read by the code. Blank lines and rows whose
`municipality` is empty are skipped.
