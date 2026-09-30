"""
Fast EADAM — Simplified EADAM (Tang & Yu, 2014; equivalent to Kesten 2010 when
all students consent), single round.

Input:
    students   : list of Student. Each must already have `preferences` ordered
                 best-first (with the bounce-back current school appended),
                 `priority_rank[school_id]` set for every ranked school, and
                 a `consent` attribute (1 = consents to waive priority).
    capacities : dict spgid -> int (non-negative capacity).

Returns:
    placements : dict student_id -> school_id. Every student is placed at some
                 school (the bounce-back guarantees individual rationality).

Invariants:
    * With every student consenting, output is the Student-Optimal Legal
      Assignment of Kesten (2010).
    * With no student consenting, output equals student-proposing DA.
    * `student.complete_preferences` is never mutated; EADAM operates on a parallel
      `student.eadam_preferences` that is initialised from it at
      the start of the call and pruned as consenting interrupting pairs are
      exposed.
"""

from collections import defaultdict


def run_eadam(students: list, capacities: dict) -> dict:
    # Initialise working preferences from the bounce-back-extended originals.
    for s in students:
        s.eadam_preferences = list(s.complete_preferences)

    # Each non-terminating pass strictly shortens at least one student's working
    # preference list, so the number of passes is bounded by the total number of
    # preference entries. Stating that bound explicitly is defensive: it turns a
    # capacity vector the underdemand test cannot resolve into a fast, loud
    # failure instead of a silent infinite loop.
    max_passes = sum(len(s.complete_preferences) for s in students) + 2
    for _ in range(max_passes):
        placements, proposers = _inner_da_with_proposals(students, capacities)
        underdemanded = _essentially_underdemanded(capacities, proposers)
        if len(underdemanded) == len(capacities):
            return placements
        _fix_matched_at_underdemanded(students, underdemanded, placements)
        _clear_unmatched(students, placements)
    raise RuntimeError(
        f"run_eadam failed to converge after {max_passes} passes: the "
        f"essentially-underdemanded set never grew to all {len(capacities)} "
        "schools. This means the capacity vector contains a school the "
        "underdemand test cannot resolve."
    )


# -----------------------------------------------------------------------------
# Inner DA (mirrors da.run_deferred_acceptance but reads eadam_preferences and
# logs the set of students that proposed to each school).
# -----------------------------------------------------------------------------
def _inner_da_with_proposals(students: list, capacities: dict) -> tuple:
    next_idx = {s.id: 0 for s in students}
    held = defaultdict(list)
    proposers = defaultdict(set)
    unassigned = [s.id for s in students]
    students_by_id = {s.id: s for s in students}

    while unassigned:
        applications = defaultdict(list)
        for sid in unassigned:
            student = students_by_id[sid]
            idx = next_idx[sid]
            if idx >= len(student.eadam_preferences):
                continue
            target = student.eadam_preferences[idx]
            applications[target].append(sid)
            proposers[target].add(sid)

        unassigned = []
        for school_id, applicants in applications.items():
            combined = held[school_id] + applicants
            cap = capacities.get(school_id, 0)
            if cap <= 0:
                held[school_id] = []
                for sid in combined:
                    next_idx[sid] += 1
                    unassigned.append(sid)
                continue
            combined.sort(key=lambda sid: students_by_id[sid].priority_rank[school_id])
            kept = combined[:cap]
            rejected = combined[cap:]
            held[school_id] = kept
            for sid in rejected:
                next_idx[sid] += 1
                unassigned.append(sid)

    placements = {}
    for school_id, holders in held.items():
        for sid in holders:
            placements[sid] = school_id
    return placements, dict(proposers)


# -----------------------------------------------------------------------------
# Essentially underdemanded schools (Tang & Yu 2014).
# -----------------------------------------------------------------------------
def _essentially_underdemanded(capacities: dict, proposers: dict) -> list:
    all_schools = list(capacities.keys())
    counts = {sch: len(proposers.get(sch, set())) for sch in all_schools}
    props = {sch: set(proposers.get(sch, set())) for sch in all_schools}
    underdemanded = []
    changed = True
    while changed:
        changed = False
        for sch in all_schools:
            if sch in underdemanded:
                continue
            # `max(..., 0)` matters: capacities can be negative when extra
            # seats are allocated by demand rather than uniformly (see
            # dynamic.py::_compute_capacities), because a school no active
            # student ranks gets 0 extra seats and is then driven below zero
            # by the students already placed there. A school that can admit
            # nobody is trivially essentially underdemanded; comparing against
            # the raw negative value instead left it permanently out of
            # `underdemanded`, so run_eadam's exit condition could never be
            # met. da.py and ttc.py already guard `cap <= 0` the same way.
            if counts[sch] <= max(capacities[sch], 0):
                underdemanded.append(sch)
                changed = True
                # Discount proposers of the newly-underdemanded school elsewhere.
                for sid in list(props[sch]):
                    for other in all_schools:
                        if other != sch and sid in props[other]:
                            props[other].discard(sid)
                            counts[other] -= 1
    return underdemanded


# -----------------------------------------------------------------------------
# Post-inner-DA preference bookkeeping.
# -----------------------------------------------------------------------------
def _fix_matched_at_underdemanded(students: list, underdemanded: list,
                                  placements: dict) -> None:
    """Collapse the working preference list of every student matched at an
    essentially underdemanded school to that single school. Non-consenting
    students additionally strip lower-priority peers' access to the schools
    they preferred over their match."""
    for student in students:
        school = placements.get(student.id)
        if school is None or school not in underdemanded:
            continue
        if student.eadam_preferences == [school]:
            continue  # already fixed in a previous iteration
        if not student.consent:
            cutoff = student.eadam_preferences.index(school)
            for preferred_school in student.eadam_preferences[:cutoff]:
                _remove_school_for_lower_priority_peers(students, student, preferred_school)
        student.eadam_preferences = [school]


def _clear_unmatched(students: list, placements: dict) -> None:
    """Students unmatched in the current inner DA are permanently out. Non-
    consenting unmatched students additionally strip lower-priority peers'
    access to every school they had preferred."""
    for student in students:
        if placements.get(student.id) is not None or not student.eadam_preferences:
            continue
        if not student.consent:
            for preferred_school in list(student.eadam_preferences):
                _remove_school_for_lower_priority_peers(students, student, preferred_school)
        student.eadam_preferences = []


def _remove_school_for_lower_priority_peers(students: list, student,
                                            preferred_school: str) -> None:
    """Remove `preferred_school` from the working preferences of every student
    whose priority_rank at `preferred_school` is strictly lower (higher rank
    number) than `student`'s."""
    my_prio = student.priority_rank.get(preferred_school)
    if my_prio is None:
        return
    for other in students:
        other_prio = other.priority_rank.get(preferred_school)
        if other_prio is None or other_prio <= my_prio:
            continue
        other.eadam_preferences = [sp for sp in other.eadam_preferences
                                   if sp != preferred_school]
