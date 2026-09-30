"""
Compute the per-run output statistics (switcher counts and shares, first-choice
placements, waiting time).

Inputs come from one (municipality, algorithm, k, iteration) run.
"""

from collections import defaultdict


STAT_COLUMNS = [
    "total_students",
    "switchers",
    "first_pref_switchers",
    "pct_switchers",
    "pct_first_pref_switchers",
    "blocking_pairs",
    "students_with_blocking_pair",
    "avg_wait_all",
    "avg_wait_switchers",
    "total_wait_all",
    "total_wait_switchers",
    "price_of_switching",
]


def compute_stats_for_market(students_assigned: list,
                              placements: dict,
                              cutoffs_per_round: dict,
                              adapted_rounds: list) -> dict:
    """
    Returns a flat dict of count statistics for one (year, grade) market.

    Percentages and averages can be computed from counts later via
    `percentages_from_counts`. We report both counts and derived values.
    """
    final_round_idx = adapted_rounds[-1].index if adapted_rounds else 0
    final_round_end = adapted_rounds[-1].end_date if adapted_rounds else None

    totals = defaultdict(float)
    totals["total_students"] = len(students_assigned)

    # Flatten cutoffs across rounds: best (= lowest) cutoff per school over time.
    best_cutoff = _best_cutoff_by_school(cutoffs_per_round)

    students_with_bp = set()
    for student in students_assigned:
        placed_school, placed_round_idx = placements.get(
            student.id, (student.current_school, final_round_idx))
        wait = _waiting_time(student, placed_round_idx, placed_school,
                              adapted_rounds, final_round_end)

        totals["total_wait_all"] += wait
        if placed_school != student.current_school:
            totals["switchers"] += 1
            totals["total_wait_switchers"] += wait
            if student.preferences and placed_school == student.preferences[0]:
                totals["first_pref_switchers"] += 1

        # Blocking pairs: schools preferred over placement where student's
        # priority was strictly better than the school's final cutoff.
        bp_count = _count_blocking_pairs(student, placed_school, best_cutoff)
        totals["blocking_pairs"] += bp_count
        if bp_count > 0:
            students_with_bp.add(student.id)

    totals["students_with_blocking_pair"] = len(students_with_bp)
    totals.update(percentages_from_counts(totals))
    return {col: totals.get(col, 0.0) for col in STAT_COLUMNS}


def percentages_from_counts(counts: dict) -> dict:
    """Derive % and average statistics from raw counts."""
    total = counts.get("total_students", 0) or 0
    switchers = counts.get("switchers", 0) or 0
    out = {}
    out["pct_switchers"] = 100.0 * switchers / total if total else 0.0
    out["pct_first_pref_switchers"] = \
        100.0 * counts.get("first_pref_switchers", 0) / total if total else 0.0
    out["avg_wait_all"] = \
        counts.get("total_wait_all", 0) / total if total else 0.0
    out["avg_wait_switchers"] = \
        counts.get("total_wait_switchers", 0) / switchers if switchers else 0.0
    out["price_of_switching"] = \
        counts.get("blocking_pairs", 0) / switchers if switchers else 0.0
    return out


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _best_cutoff_by_school(cutoffs_per_round: dict) -> dict:
    """Across all rounds, track each school's best (lowest) admitted rank."""
    best = {}
    for _, per_school in cutoffs_per_round.items():
        for school_id, cut in per_school.items():
            if school_id not in best or cut > best[school_id]:
                best[school_id] = cut
    return best


def _waiting_time(student, placed_round_idx, placed_school,
                   adapted_rounds, final_round_end):
    """Days from application to placement (or year-end if never switched)."""
    if placed_school == student.current_school or placed_round_idx is None:
        end = final_round_end
    else:
        end = next((r.end_date for r in adapted_rounds
                    if r.index == placed_round_idx), final_round_end)
    if end is None or student.application_date is None:
        return 0.0
    return max(0, (end - student.application_date).days)


def _count_blocking_pairs(student, placed_school, best_cutoff) -> int:
    """For each school the student prefers over their placement, check cutoffs."""
    if placed_school not in student.complete_preferences:
        return 0
    placed_idx = student.complete_preferences.index(placed_school)
    count = 0
    for school_id in student.complete_preferences[:placed_idx]:
        cut = best_cutoff.get(school_id)
        if cut is None:
            continue
        rank = student.priority_rank.get(school_id)
        if rank is not None and rank < cut:
            count += 1
    return count
