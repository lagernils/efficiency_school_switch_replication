"""
Top Trading Cycles (single round).

Simple, readable implementation of the graph-cycle version: students point to
their best remaining school with capacity, schools point to their
highest-priority remaining student, and every cycle trades.
"""

from collections import defaultdict

from .preprocessing import priority_sort_key


def run_top_trading_cycles(students: list, capacities: dict) -> dict:
    """
    students  : list of Student with preferences and priority_rank already set.
    capacities: dict spgid -> int.

    Returns placements: dict student_id -> school_id. Students whose
    preferences are exhausted are placed at their own bounce-back (which is
    the last element of their preference list).
    """
    pref_idx = {s.id: 0 for s in students}          # next preference to try
    remaining_cap = dict(capacities)
    students_by_id = {s.id: s for s in students}

    # For each school, queue of remaining students sorted by priority (best first).
    queue_by_school = _build_school_queues(students)
    sch_pointer = {sid: 0 for sid in queue_by_school}      # first alive student in queue

    alive_students = set(s.id for s in students)
    placements = {}

    while alive_students:
        # --- 1. Build current edges: student -> preferred school; school -> top student.
        student_to_school = {}
        for sid in list(alive_students):
            target = _next_school_with_capacity(
                students_by_id[sid], pref_idx, remaining_cap)
            if target is None:
                # Exhausted. Place on bounce-back (last preference is current school).
                placements[sid] = students_by_id[sid].complete_preferences[-1]
                alive_students.remove(sid)
            else:
                student_to_school[sid] = target

        if not alive_students:
            break

        school_to_student = {}
        for school_id, queue in queue_by_school.items():
            if remaining_cap.get(school_id, 0) <= 0:
                continue
            top = _next_alive_in_queue(queue, sch_pointer, school_id, alive_students)
            if top is not None:
                school_to_student[school_id] = top

        # --- 2. Find cycles in the bipartite map student <-> school.
        cycles = _find_cycles(student_to_school, school_to_student)

        if not cycles:
            # No cycle: everyone remaining points out of the graph.
            # This can happen if all remaining students target schools whose
            # top student isn't one of them. Fall back to bounce-back.
            for sid in list(alive_students):
                placements[sid] = students_by_id[sid].complete_preferences[-1]
                alive_students.remove(sid)
            break

        # --- 3. Execute trades.
        for cycle in cycles:
            for sid, school_id in cycle:
                placements[sid] = school_id
                remaining_cap[school_id] = remaining_cap.get(school_id, 0) - 1
                alive_students.discard(sid)

    return placements


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _build_school_queues(students: list) -> dict:
    """Return dict school_id -> list of student_ids sorted by priority (best first).

    EVERY student is queued at EVERY school, not only those who ranked it. In
    TTC (Abdulkadiroglu and Sonmez, 2003) a school points to the highest-priority
    student remaining in the market, whoever that is -- if that student wants a
    different school the chain simply dead-ends, and the seat waits until they
    have been assigned and removed. Queueing only a school's own applicants
    would let it trade immediately with its best applicant instead, which is a
    different algorithm.

    The two coincide when there is no spare capacity, because a school only has
    a seat when its own current students occupy it and those students hold top
    priority there. They diverge once empty seats are added, so this matters for
    the capacity counterfactual.

    Priority order comes from preprocessing.priority_sort_key rather than from
    `student.priority_rank`, which is only populated for schools a student
    actually ranked.
    """
    all_schools = set()
    for s in students:
        all_schools.update(s.complete_preferences)
    return {
        school_id: [s.id for s in sorted(
            students, key=lambda s: priority_sort_key(s, school_id))]
        for school_id in all_schools
    }


def _next_school_with_capacity(student, pref_idx, remaining_cap):
    while pref_idx[student.id] < len(student.complete_preferences):
        sid = student.complete_preferences[pref_idx[student.id]]
        if remaining_cap.get(sid, 0) > 0:
            return sid
        pref_idx[student.id] += 1
    return None


def _next_alive_in_queue(queue, pointer, school_id, alive_students):
    idx = pointer[school_id]
    while idx < len(queue) and queue[idx] not in alive_students:
        idx += 1
    pointer[school_id] = idx
    return queue[idx] if idx < len(queue) else None


def _find_cycles(student_to_school: dict, school_to_student: dict) -> list:
    """
    Each student has out-degree 1 (to a school); each school has out-degree 1
    (to a student). Walk from each node once and detect revisits.
    """
    cycles = []
    visited_students = set()

    for start in list(student_to_school.keys()):
        if start in visited_students:
            continue
        path = []
        path_set = set()
        cur_student = start
        while cur_student is not None and cur_student not in visited_students:
            if cur_student in path_set:
                # Found a cycle starting from where cur_student first appeared.
                cut = next(i for i, (sid, _) in enumerate(path) if sid == cur_student)
                cycle = path[cut:]
                cycles.append(cycle)
                visited_students.update(sid for sid, _ in cycle)
                break
            school_id = student_to_school.get(cur_student)
            if school_id is None:
                break
            path.append((cur_student, school_id))
            path_set.add(cur_student)
            cur_student = school_to_student.get(school_id)
        visited_students.update(sid for sid, _ in path)
    return cycles
