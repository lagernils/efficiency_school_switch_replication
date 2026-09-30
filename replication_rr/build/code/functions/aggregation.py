"""
Aggregation utilities:
  * across markets within one run (sum counts, recompute derived)
  * across Monte Carlo iterations (mean + std)
  * across municipalities (law of total variance)
"""

from collections import defaultdict
import math
import pandas as pd

from .stats import STAT_COLUMNS, percentages_from_counts


# -----------------------------------------------------------------------------
# Within-run: combine several (year,grade) markets into one summary for a run.
# -----------------------------------------------------------------------------
COUNT_COLS = [
    "total_students", "switchers", "first_pref_switchers",
    "blocking_pairs", "students_with_blocking_pair",
    "total_wait_all", "total_wait_switchers",
]


def combine_markets(market_stats: list) -> dict:
    """`market_stats` is a list of per-market stat dicts."""
    totals = defaultdict(float)
    for m in market_stats:
        for col in COUNT_COLS:
            totals[col] += m.get(col, 0)
    totals.update(percentages_from_counts(totals))
    return {col: totals.get(col, 0.0) for col in STAT_COLUMNS}


# -----------------------------------------------------------------------------
# Across iterations: compute (mean, std) for each k.
# -----------------------------------------------------------------------------
def summarise_iterations(runs_by_k: dict) -> pd.DataFrame:
    """
    runs_by_k : dict k -> list of run-summaries (each a dict of STAT_COLUMNS).
    Returns DataFrame with columns k, {stat}_mean, {stat}_std.
    """
    rows = []
    for k, runs in sorted(runs_by_k.items()):
        row = {"k": k}
        for col in STAT_COLUMNS:
            values = [r[col] for r in runs]
            row[f"{col}_mean"] = _mean(values)
            row[f"{col}_std"] = _std(values)
        rows.append(row)
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Across municipalities: applicant-weighted means + law of total variance.
# -----------------------------------------------------------------------------
def aggregate_across_municipalities(per_mun_dfs: dict) -> pd.DataFrame:
    """
    per_mun_dfs : dict municipality -> DataFrame produced by summarise_iterations.
    Returns DataFrame with same columns (indexed by k).
    """
    if not per_mun_dfs:
        return pd.DataFrame()

    # Collect all k values.
    all_ks = sorted({k for df in per_mun_dfs.values() for k in df["k"].tolist()})
    rows = []
    for k in all_ks:
        row = {"k": k}
        # Per-municipality n (mean total_students) weights the aggregation.
        weights = {}
        stat_values = {col: [] for col in STAT_COLUMNS}
        stat_stds = {col: [] for col in STAT_COLUMNS}
        for mun, df in per_mun_dfs.items():
            sub = df[df["k"] == k]
            if sub.empty:
                continue
            weights[mun] = sub["total_students_mean"].iloc[0]
            for col in STAT_COLUMNS:
                stat_values[col].append(sub[f"{col}_mean"].iloc[0])
                stat_stds[col].append(sub[f"{col}_std"].iloc[0])

        N = sum(weights.values())
        mun_list = list(weights.keys())
        for col in STAT_COLUMNS:
            means = stat_values[col]
            stds = stat_stds[col]

            if col in COUNT_COLS:
                # Count-type: sum across municipalities.
                grand_mean = sum(means)
                # Law of total variance using within-municipality std and
                # between-municipality spread of means, applicant-weighted.
                grand_std = _law_of_total_var(
                    means, stds,
                    [weights[m] for m in mun_list], N)
                row[f"{col}_mean"] = grand_mean
                row[f"{col}_std"] = grand_std
            else:
                row[f"{col}_mean"] = None     # filled below from counts
                row[f"{col}_std"] = None

        # Rebuild derived stats from the aggregated counts.
        agg_counts = {c: row[f"{c}_mean"] for c in COUNT_COLS}
        derived = percentages_from_counts(agg_counts)
        for col, val in derived.items():
            row[f"{col}_mean"] = val
            row[f"{col}_std"] = 0.0       # derived std not reported

        rows.append(row)
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Low-level helpers
# -----------------------------------------------------------------------------
def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _std(values):
    if len(values) <= 1:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def _law_of_total_var(means, stds, weights, N):
    """Within-group variance + between-group variance, weighted by applicants."""
    if not means or N == 0:
        return 0.0
    weighted_grand_mean = sum(w * m for w, m in zip(weights, means)) / N
    within = sum(w * (s ** 2) for w, s in zip(weights, stds)) / N
    between = sum(w * (m - weighted_grand_mean) ** 2
                  for w, m in zip(weights, means)) / N
    return math.sqrt(within + between)
