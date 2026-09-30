"""
Date randomisation, priority-rank assignment, and bounce-back enforcement.
"""

import random
from datetime import date, timedelta

from . import config
from .types import Student


# -----------------------------------------------------------------------------
# Randomise each student's application date within its original half-year
# -----------------------------------------------------------------------------
# The offset is drawn from Random(f"{CURRENT_SEED}:date:{participantId}")
# rather than from the shared stream, mirroring the lottery number in
# data_loading.py: it then depends only on the seed and the participant id, not
# on how many numbers were drawn before it. That is what lets `original` and
# `replication_rr` be compared draw-for-draw rather than only in distribution.
# `config.CURRENT_SEED` is set per iteration by Run_School_Switch.run_loop in
# run_school_switch.py.
def randomise_application_dates(students: list,
                                 overall_min: date,
                                 overall_max: date) -> None:
    """Replace each Student.application_date in place."""
    for s in students:
        s.application_date = _draw_random_date(
            s.application_date, overall_min, overall_max, s.id)


def _draw_random_date(original: date, overall_min: date,
                      overall_max: date, participant_id: str) -> date:
    """Draw uniformly from the original half-year, clipped to overall bounds."""
    year = original.year
    if original.month <= 6:
        lo = date(year, 1, 1)
        hi = date(year, 6, 29)
    else:
        lo = date(year, 7, 1)
        hi = date(year, 12, 31)
    if overall_min is not None:
        lo = max(lo, overall_min)
    if overall_max is not None:
        hi = min(hi, overall_max)
    if hi < lo:
        return original
    days = (hi - lo).days
    offset = 0 if days <= 0 else random.Random(
        f"{config.CURRENT_SEED}:date:{participant_id}").randint(0, days)
    return lo + timedelta(days=offset)


# -----------------------------------------------------------------------------
# Bounce-back: append current school if not already ranked
# -----------------------------------------------------------------------------
def append_bounce_back(students: list) -> None:
    """Build `complete_preferences` = the submitted ROL with the student's
    current school appended if they did not rank it themselves.

    `preferences` is left untouched and always means "the rank-ordered list the
    student submitted". Everything the algorithms propose over reads
    `complete_preferences`; anything reasoning about demand (which programs
    students actually asked for) reads `preferences`. Keeping the two apart
    removes an ordering trap: `allocate_extra_seats` would count every student
    as demanding their own current school if it ran after a version of this
    function that mutated `preferences` in place.
    """
    for s in students:
        s.complete_preferences = list(s.preferences)
        if s.current_school not in s.complete_preferences:
            s.complete_preferences.append(s.current_school)


# -----------------------------------------------------------------------------
# Priority-rank computation, STB mode (random_priorities=True)
# -----------------------------------------------------------------------------
def priority_sort_key(student, school_id: str):
    """Sort key giving a school's priority order under single tie-breaking:
    the school's own current students first, then everyone else, each ordered
    by lottery number (low = better).

    Defined once here because two callers need it. `assign_priority_ranks`
    below uses it for the students who ranked a school; `ttc._build_school_queues`
    needs it for *every* student, including those who did not rank the school,
    and those students have no entry in `priority_rank`.
    """
    return (0 if student.current_school == school_id else 1, student.lottery_number)


def assign_priority_ranks(students: list) -> None:
    """
    For each school that any student in the group ranks, assign an integer rank
    (1 = best) to every student who ranks that school. Under STB:
      incumbents (current school == s) come first, ranked by lottery number;
      non-incumbents follow, also ranked by lottery number.
    """
    # Collect, for each school, the students who ranked it.
    relevant = {}           # school_id -> list[Student]
    for student in students:
        # complete_preferences, not preferences: a student must have a priority
        # rank at their bounce-back school too, or the algorithms cannot place
        # them there.
        for school_id in student.complete_preferences:
            relevant.setdefault(school_id, []).append(student)

    for school_id, cohort in relevant.items():
        cohort_sorted = sorted(cohort, key=lambda s: priority_sort_key(s, school_id))
        for rank, student in enumerate(cohort_sorted, start=1):
            student.priority_rank[school_id] = rank
