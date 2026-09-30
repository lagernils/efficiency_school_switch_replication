"""Utilities for updating adapted rounds.

Provides a small `Update_Round` class with a `get()` entrypoint. The
module imports the `Student` and `School` dataclasses so editors and
type-checkers can recognize those attributes on passed objects.
"""
import copy
from typing import Tuple, List
from functions.get_data import Student, School, PlacementRound


def allocate_extra_seats(market_students: List[Student], overcapacity_pct: float,
                         demand_proportional: bool) -> dict:
    """Distribute a market-level budget of additional (empty) seats across the
    programs of one (year, grade) market.

    The budget is defined exactly as the paper defines the x-axis of the
    capacity figure -- additional seats as a percentage of active students:

        budget = round(overcapacity_pct / 100 * len(market_students))

    and is allocated across P, the set of programs appearing in at least one
    student's rank-ordered list.

      demand_proportional=False : split as evenly as possible across P.
      demand_proportional=True  : split in proportion to demand(p), the number
                                  of students in the market who rank p anywhere.

    Both branches use largest-remainder (Hamilton) rounding, so the seats handed
    out sum to `budget` exactly and the two allocation modes are directly
    comparable at any given overcapacity_pct.

    Reads `student.preferences` (the submitted ROL), NOT
    `student.complete_preferences` (which has the bounce-back current school
    appended), so a student is never counted as demanding the school they
    already attend. Because the two are separate attributes, this holds
    regardless of when this function is called.
    """
    if not market_students or overcapacity_pct <= 0:
        return {}

    programs = sorted({p for st in market_students for p in st.preferences})
    if not programs:
        return {}

    budget = int(round(overcapacity_pct / 100.0 * len(market_students)))
    if budget <= 0:
        return {}

    if demand_proportional:
        demand = {p: 0 for p in programs}
        for st in market_students:
            for p in st.preferences:
                demand[p] += 1
        total = sum(demand.values())
        weights = ({p: demand[p] / total for p in programs} if total > 0
                   else {p: 1.0 / len(programs) for p in programs})
    else:
        weights = {p: 1.0 / len(programs) for p in programs}

    quota = {p: budget * weights[p] for p in programs}
    seats = {p: int(quota[p]) for p in programs}
    # Largest remainder: hand the leftover seats to the largest fractional
    # parts, breaking ties on program id so the result is deterministic.
    leftover = budget - sum(seats.values())
    if leftover > 0:
        order = sorted(programs, key=lambda p: (-(quota[p] - seats[p]), p))
        for p in order[:leftover]:
            seats[p] += 1
    return seats


class Update_Round:
    """Class for updating rounds within dynamic algorithms.
    """

    def update_school_capacities(self, students: List[Student], schools: List[School], students_without_placement: List[Student], students_with_placement: List[Student], base_capacity: int, extra_seats: dict = None) -> List[School]:
        """Update school capacities based on current students with guarantees.

        `extra_seats` is an optional program -> seats mapping produced once per
        (year, grade) market by `allocate_extra_seats`. When it is None, every
        school is seeded at `base_capacity`, which is the paper's baseline
        behaviour and leaves published results untouched."""
        # Count current students per school
        for school in schools:
            # Reset capacity to the school's extra-seat allowance before counting
            school.capacity = (base_capacity if extra_seats is None
                               else extra_seats.get(school.spgid, 0))
            for student in students:
                if student.current_school_spg == school.spgid:
                    school.capacity += 1 # if student in current round is current student, increase capacity by 1
            if len(students_with_placement) == 0:
                continue  # No adjustments needed if no students with placement
            for student in students_with_placement:
                if student.current_school_spg == school.spgid:
                    school.capacity += 1 # if a current student has gotten a new placement, increase capacity by 1
                else:
                    if student.placement[school.spgid]:
                        school.capacity -= 1 # if a non-current student has gotten a placement at this school, decrease capacity by 1

            school.available_seats = school.capacity  # Reset available seats

        return schools
    
    def get_students_without_placement(self, students: List[Student], schools: List[School]) -> List[Student]:
        """Return list of students without a placement."""
        for student in students:
            if student.current_school_spg not in student.placement:
                print(f"Missing current_school_spg in placement dict:")
                print(f"  Student participantid: {student.participantid}, raw PR: {student.placementround_raw}, grade: {student.grade}, year: {student.year}")
                print(f"  current_school_spg: {student.current_school_spg}")
                print(f"  placement keys: {list(student.placement.keys())}")
                raise KeyError(f"current_school_spg {student.current_school_spg} not in placement dict for student {student.participantid}")
        students_without_placement = [student for student in students if student.placement[student.current_school_spg]] # student not placed if placed at current school
        #self.verify_optimal_stable(students_without_placement, schools)
        for student in students_without_placement:
            student.placement = {}
            student.preliminary_placed = False
            student.application_history = []
        return students_without_placement
    
    def verify_Pareto_efficiency(self, students_without_placement: List[Student], students_with_placement_for_this_round: List[Student], schools: List[School]) -> None:
        """Checks a necessary condition for Pareto efficiency. Not a full check of Pareto efficiency, but checks the following:
        For each student i without placement, consider each preferred school A (over current school B). 
        For each such school A, consider each current unplaced student j at school A who has ranked school B (thus would prefer B over current placement at A). 
        Student i and student j would prefer switching schools. Such a pair should not exist if placement is Pareto efficient."""
        id_to_student = {student.participantid: student for student in students_without_placement}
        id_to_school = {school.spgid: school for school in schools}
        for student in students_without_placement:
            for preferred_spgid in student.preferences:
                if preferred_spgid == student.current_school_spg:
                    break  # reached current school, no need to check less preferred schools
                # Check if there is a student with placement at preferred school who would switch with student without placement
                for other_student_id in id_to_school[preferred_spgid].current_students:
                    if other_student_id in id_to_student: # other student is also without placement, so would switch with student
                        other_student = id_to_student[other_student_id]
                        if other_student.preferences_dict[student.current_school_spg] is not None: # if other student has ranked current school of student without placement
                            if other_student.preferences_dict[student.current_school_spg] < other_student.preferences_dict[preferred_spgid]: # if other student prefers current school of student without placement over their current preferred school
                                print('Found a potential Pareto improvement!')
                                print('Student without placement', student.participantid, 'wishes to switch to', preferred_spgid, 'from ', student.current_school_spg)
                                print('Student', other_student.participantid, 'is a current student at', preferred_spgid, 'and would switch to', student.current_school_spg)
                                raise ValueError('Pareto efficiency violated: found a student without placement who could switch with a current student to a more preferred school.')
        #print('No break of Pareto efficiency found for students without placement.')
    
    def verify_optimal_stable(self, students_without_placement: List[Student], students_with_placement_for_this_round: List[Student], schools: List[School]) -> None:
        """Not a full check of placement being student-optimal stable, but checks the following:
        For each student i without placement, consider each preferred school A (over current school B).
        For each such school A, consider each current student j at school A who has ranked school B (thus would prefer B over current placement at A).
        Student i and student j would prefer switching schools.
        If placement is student-optimal stable, there must exist a student k (either without placement or placed in this round)
        who blocks this switch by having justified envy against either student (i,A) or student (j,B).
        If no such student k exists, raise ValueError("Optimal stability violated)
        ."""
        id_to_student = {student.participantid: student for student in students_without_placement}
        id_to_school = {school.spgid: school for school in schools}
        for student in students_without_placement: # student i, with current school B
            for preferred_spgid in student.preferences: # loop over all preferred schools of student i
                # Refer to preferred school of student i as school A
                # Get current students at school A without placements that has ranked school B (thus would prefer school B over current placement at A)
                potential_switchers = self._get_potential_switchers(student.current_school_spg, id_to_school[preferred_spgid].current_students , id_to_student)
                if not potential_switchers:
                    continue  # no potential switchers, move on to next student
                for switcher_tuple in potential_switchers: # loop over potential switchers j
                    # Check if there exists a blocker student k among unplaced students that would block the switch
                    blocker_found = self._check_for_blockers_among_unplaced(student, preferred_spgid, switcher_tuple, students_without_placement)
                    if not blocker_found:
                        # If no blocker found among unplaced students, check among placed students
                        blocker_found = self._check_for_blockers_among_placed(student, preferred_spgid, switcher_tuple, students_with_placement_for_this_round)
                        if not blocker_found:
                            print('Found a potential switch that would not create a blocking pair!')
                            print('Student without placement', student.participantid, 'wishes to switch to', preferred_spgid, 'from ', student.current_school_spg)
                            print('Student', switcher_tuple[0], 'is a current student at', preferred_spgid, 'and would switch to', student.current_school_spg)
                            raise ValueError('Optimal stability violated: found a student without placement who could switch with a current student without creating a blocking pair.')
        print('No break of optimal stability found for students without placement.')


    def _get_potential_switchers(self, current_school_spg: str, current_students_at_preferred_spgid: List[str], id_to_student: dict) -> List[Tuple[str, int]]:
        """Get potential switchers for a given student."""
        potential_switchers = []
        for current_student_id in current_students_at_preferred_spgid: #for student j at school A
            if current_student_id in id_to_student: # student j is also without placement
                current_student_obj = id_to_student[current_student_id] 
                for preferred_switch_spg in current_student_obj.preferences: # loop over all preferred schools of student j
                    if preferred_switch_spg == current_school_spg: # if student j has ranked school B (thus prefers over their current placement A)
                        potential_switcher_tuple = (current_student_id, current_student_obj.prio_score[preferred_switch_spg])
                        potential_switchers.append(potential_switcher_tuple)
        return potential_switchers
    
    def _check_for_blockers_among_unplaced(self, student_i: Student, preferred_spgid: str, switcher_tuple: Tuple[str, int], students_without_placement: List[Student]) -> bool:
        """Check for blockers among unplaced students."""
        blocker_found = False
        for possible_blocker_student in students_without_placement: # loop over any other unplaced student k
            if possible_blocker_student.preferences_dict[student_i.current_school_spg] is not None: # if possible blocker student k ranks school B (thus prefers B over their current placement)
                if possible_blocker_student.prio_score[student_i.current_school_spg] < switcher_tuple[1]: # if student k has better priority score than switcher j
                    blocker_found = True # blocker student k would exhibit justified envy to student j and school B
            if possible_blocker_student.preferences_dict[preferred_spgid] is not None: # if blocker student k ranks preferred school A of student i (thus prefers A over their current placement)
                if possible_blocker_student.prio_score[preferred_spgid] < student_i.prio_score[preferred_spgid]: # if blocker student k has better priority score than student i
                    blocker_found = True # blocker student k would exhibit justified envy to student i and school A
        return blocker_found
    
    def _check_for_blockers_among_placed(self, student_i: Student, preferred_spgid: str, switcher_tuple: Tuple[str, int], students_with_placement_for_this_round: List[Student]) -> bool:
        """Check for blockers among placed students."""
        blocker_found = False
        for possible_blocker_student in students_with_placement_for_this_round: # loop over any placed student k
            for spgid, placement_bool in possible_blocker_student.placement.items():
                if placement_bool:
                    placement_rank = possible_blocker_student.preferences_dict[spgid] # rank of placement school of student k
            for blocker_preferred_spgid in possible_blocker_student.preferences: # loop over all preferred schools of student k
                if blocker_preferred_spgid == student_i.current_school_spg: # if student k has ranked school B
                    if possible_blocker_student.preferences_dict[blocker_preferred_spgid] < placement_rank: # if student k prefers school B over their placement
                        if possible_blocker_student.prio_score[blocker_preferred_spgid] < switcher_tuple[1]: # if student k has better priority score than switcher j to school B
                            blocker_found = True # blocker student k would exhibit justified envy to student j and school B
                if blocker_preferred_spgid == preferred_spgid: # if student k has ranked school A
                    if possible_blocker_student.preferences_dict[blocker_preferred_spgid] < placement_rank: # if student k prefers school A over their placement
                        if possible_blocker_student.prio_score[blocker_preferred_spgid] < student_i.prio_score[preferred_spgid]: # if student k has better priority score to school A than student i
                            blocker_found = True # blocker student k would exhibit justified envy to student i and school A
        return blocker_found
        
            
    
    def update_placement_documentation(self, students: List[Student]) -> List[Student]:
        """Update placement documentation for all students after DA."""
        for student in students:
            # reset documentation
            student.documentation_placement = copy.deepcopy(student.placement)
            student.documentation_application_history = copy.deepcopy(student.application_history)
        return students
    
    def add_placement_info(self, students: List[Student], placement_round_obj: PlacementRound) -> List[Student]:
        """Add placement round info to placed students."""
        for student in students:
            #student.placed_in_round = placement_round_obj.id
            student.placement_pr = placement_round_obj.id
            student.placement_date = placement_round_obj.application_end
        return students