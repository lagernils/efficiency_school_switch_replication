from typing import List, Dict, Set, Tuple
from functions.get_data import School
from functions.get_data import Student


class EADAM_helper:

    # -------------------------------------------------------------------------
    # Inner DA: a single run of student-proposing DA, adapted to read from
    # `student.eadam_preferences` (NOT `complete_preferences`) and to log the
    # set of students who ever proposed to each school.
    # -------------------------------------------------------------------------
    def run_inner_DA(self, students: List[Student], schools: List[School]) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
        """Run a single round of student-proposing DA on `eadam_preferences`.
        Returns (match, proposers) where match is participantid -> spgid (None if
        the student ended up unmatched) and proposers[spgid] is the set of
        participantids that proposed to that school at any point in the run."""
        capacity = {sc.spgid: sc.capacity for sc in schools}
        held: Dict[str, List[str]] = {sc.spgid: [] for sc in schools}
        proposers: Dict[str, Set[str]] = {sc.spgid: set() for sc in schools}
        next_prop = {s.participantid: 0 for s in students}
        prio_score = {s.participantid: dict(s.prio_score) for s in students}
        prefs = {s.participantid: list(s.eadam_preferences) for s in students}

        unassigned = [s.participantid for s in students]
        while unassigned:
            still_unassigned = []
            for pid in unassigned:
                if next_prop[pid] >= len(prefs[pid]):
                    continue  # exhausted preferences
                spgid = prefs[pid][next_prop[pid]]
                next_prop[pid] += 1
                if spgid not in prio_score[pid]:
                    still_unassigned.append(pid)
                    continue  # school finds student unacceptable
                proposers[spgid].add(pid)
                if capacity[spgid] <= 0:
                    still_unassigned.append(pid)
                    continue
                held[spgid].append(pid)
                held[spgid].sort(key=lambda p: prio_score[p][spgid])  # ascending = best first
                if len(held[spgid]) > capacity[spgid]:
                    rejected = held[spgid].pop()
                    still_unassigned.append(rejected)
            unassigned = still_unassigned

        match = {s.participantid: None for s in students}
        for spgid, holders in held.items():
            for pid in holders:
                match[pid] = spgid
        return match, proposers

    # -------------------------------------------------------------------------
    # Essentially underdemanded schools (Tang & Yu 2014).
    # -------------------------------------------------------------------------
    def get_essentially_underdemanded(self, schools: List[School], proposers: Dict[str, Set[str]]) -> List[str]:
        """Transitively find schools with at most `capacity` proposals, ignoring
        proposals from students already matched to an underdemanded school."""
        capacity = {sc.spgid: sc.capacity for sc in schools}
        counts = {sc.spgid: len(proposers[sc.spgid]) for sc in schools}
        props = {sc.spgid: set(proposers[sc.spgid]) for sc in schools}
        underdemanded: List[str] = []
        changed = True
        while changed:
            changed = False
            for school in schools:
                if school.spgid in underdemanded:
                    continue
                # `max(..., 0)` matters: capacities can be negative when extra
                # seats are allocated by demand rather than uniformly (see
                # update_round.allocate_extra_seats) -- a school no active
                # student ranks gets zero extra seats and is then driven below
                # zero by students already placed there. A school that can
                # admit nobody is trivially essentially underdemanded;
                # comparing against the raw negative value leaves it
                # permanently out of `underdemanded`, so EADAM.run()'s exit
                # condition could never be met and the loop would never end.
                if counts[school.spgid] <= max(capacity[school.spgid], 0):
                    underdemanded.append(school.spgid)
                    changed = True
                    for pid in list(props[school.spgid]):
                        for other in schools:
                            if other.spgid != school.spgid and pid in props[other.spgid]:
                                props[other.spgid].discard(pid)
                                counts[other.spgid] -= 1
        return underdemanded

    # -------------------------------------------------------------------------
    # Inter-round preference bookkeeping.
    # -------------------------------------------------------------------------
    def fix_matched_at_underdemanded(self, students: List[Student], schools: List[School], underdemanded: List[str], match: Dict[str, str]) -> None:
        """Collapse the working preference list of every student matched at an
        essentially underdemanded school to just that school. Non-consenting
        students additionally strip their lower-priority peers' access to any
        school they preferred over their match."""
        for student in students:
            spgid = match.get(student.participantid)
            if spgid is None or spgid not in underdemanded:
                continue
            if student.eadam_preferences == [spgid]:
                continue  # already fixed in a previous iteration
            if not student.consent:
                cutoff = student.eadam_preferences.index(spgid)
                preferred_over_match = student.eadam_preferences[:cutoff]
                for preferred_spgid in preferred_over_match:
                    self._remove_school_for_lower_priority_peers(students, schools, student, preferred_spgid)
            student.eadam_preferences = [spgid]

    def clear_unmatched_students(self, students: List[Student], schools: List[School], match: Dict[str, str]) -> None:
        """Students unmatched in the current inner-DA are permanently out. Non-
        consenting unmatched students additionally strip their lower-priority peers'
        access to every school they had preferred."""
        for student in students:
            if match.get(student.participantid) is not None or not student.eadam_preferences:
                continue
            if not student.consent:
                for preferred_spgid in list(student.eadam_preferences):
                    self._remove_school_for_lower_priority_peers(students, schools, student, preferred_spgid)
            student.eadam_preferences = []

    def _remove_school_for_lower_priority_peers(self, students: List[Student], schools: List[School], student: Student, preferred_spgid: str) -> None:
        """Remove `preferred_spgid` from the working preferences of every student
        whose priority at `preferred_spgid` is strictly lower than `student`'s."""
        my_prio = student.prio_score.get(preferred_spgid)
        if my_prio is None:
            return
        for other in students:
            other_prio = other.prio_score.get(preferred_spgid)
            if other_prio is None or other_prio <= my_prio:
                continue
            other.eadam_preferences = [sp for sp in other.eadam_preferences if sp != preferred_spgid]

    # -------------------------------------------------------------------------
    # Mirror of DA_helper.update_* methods to keep attribute semantics identical
    # across DA, TTC, and EADAM.
    # -------------------------------------------------------------------------
    def update_student_placement_attribute(self, students: List[Student], schools: List[School], match: Dict[str, str]) -> None:
        """Set `student.placement[spgid]` = (spgid == matched school) for every school."""
        for student in students:
            placed_spgid = match.get(student.participantid)
            for school in schools:
                student.placement[school.spgid] = (school.spgid == placed_spgid)

    def update_school_available_seats(self, schools: List[School], match: Dict[str, str]) -> None:
        """`school.available_seats = school.capacity - #placed at this school`."""
        counts: Dict[str, int] = {sc.spgid: 0 for sc in schools}
        for pid, spgid in match.items():
            if spgid is not None:
                counts[spgid] = counts.get(spgid, 0) + 1
        for school in schools:
            school.available_seats = school.capacity - counts.get(school.spgid, 0)

    def update_school_cutoff(self, students: List[Student], schools: List[School], match: Dict[str, str]) -> None:
        """Mirror DA_helper.update_school_cutoff: set cutoff to the worst priority
        actually admitted when the school is at capacity, else a big sentinel."""
        spgid_to_placed: Dict[str, List[Student]] = {sc.spgid: [] for sc in schools}
        for student in students:
            placed = match.get(student.participantid)
            if placed is not None:
                spgid_to_placed[placed].append(student)
        for school in schools:
            placed_students = spgid_to_placed.get(school.spgid, [])
            if len(placed_students) == school.capacity:
                if placed_students:
                    school.cutoff = max(s.prio_score[school.spgid] for s in placed_students)
                else:
                    school.cutoff = 0
            else:
                school.cutoff = 1000000
