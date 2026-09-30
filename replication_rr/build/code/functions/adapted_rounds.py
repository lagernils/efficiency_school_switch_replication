"""
Divide an academic year into consecutive k-day intervals.

The academic year starts June 30 of year t and ends June 29 of year t+1.
"""

from datetime import date, timedelta
from .types import AdaptedRound


def build_adapted_rounds(year: int, grade: int, k: int) -> list:
    """Return list of AdaptedRound objects covering the academic year."""
    start = date(year, 6, 30)
    end = date(year + 1, 6, 29)

    rounds = []
    cur = start
    idx = 1
    while cur <= end:
        window_end = min(cur + timedelta(days=k - 1), end)
        rounds.append(AdaptedRound(
            index=idx, year=year, grade=grade,
            start_date=cur, end_date=window_end,
        ))
        cur = window_end + timedelta(days=1)
        idx += 1
    return rounds


def assign_students_to_rounds(students: list, adapted_rounds: list) -> list:
    """
    Attach each student to the adapted round whose window contains their
    application_date. Students outside the window are silently dropped.
    Returns the list of students actually assigned (useful for downstream
    totals).
    """
    assigned = []
    for s in students:
        for r in adapted_rounds:
            if r.start_date <= s.application_date <= r.end_date:
                r.students.append(s)
                assigned.append(s)
                break
    return assigned
