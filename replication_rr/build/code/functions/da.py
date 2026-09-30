"""
Student-proposing Deferred Acceptance (single round).

Input:
    students  : list of Student. Each must already have `preferences` ordered
                best-first (with the bounce-back current school appended) and
                `priority_rank[school_id]` set for every school in its list.
    capacities: dict spgid -> int (non-negative capacity).

Returns:
    placements : dict student_id -> school_id (every student placed somewhere,
                 possibly their bounce-back school).
"""

from collections import defaultdict


def run_deferred_acceptance(students: list, capacities: dict) -> dict:
    next_choice_idx = {s.id: 0 for s in students}   # pointer into preferences
    held = defaultdict(list)                         # school -> list of student ids
    unassigned = [s.id for s in students]
    students_by_id = {s.id: s for s in students}

    while unassigned:
        # Each unassigned student applies to their next preferred school.
        applications = defaultdict(list)
        for sid in unassigned:
            student = students_by_id[sid]
            idx = next_choice_idx[sid]
            if idx >= len(student.complete_preferences):
                continue                             # should not happen with bounce-back
            target = student.complete_preferences[idx]
            applications[target].append(sid)

        unassigned = []

        # Each school considers current holds + new applications together.
        for school_id, applicants in applications.items():
            combined = held[school_id] + applicants
            cap = capacities.get(school_id, 0)
            if cap <= 0:
                # No capacity at all: everyone is rejected.
                held[school_id] = []
                for sid in combined:
                    next_choice_idx[sid] += 1
                    unassigned.append(sid)
                continue
            combined.sort(key=lambda sid: students_by_id[sid].priority_rank[school_id])
            kept = combined[:cap]
            rejected = combined[cap:]
            held[school_id] = kept
            for sid in rejected:
                next_choice_idx[sid] += 1
                unassigned.append(sid)

    placements = {}
    for school_id, holders in held.items():
        for sid in holders:
            placements[sid] = school_id
    return placements
