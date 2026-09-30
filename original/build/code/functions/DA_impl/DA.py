import time

from typing import List
from functions.get_data import School
from functions.get_data import Student
from .DA_helper import DA_helper


class DA():

    def __init__(self):
        self.tick = time.time()

    def DA_recursive(self, students: List[Student], schools: List[School], id_to_school: dict, id_to_student: dict, placements: dict, guaranteed_current_seat_bool: bool, i: int):
        """This is where school_placements are actually made and can be seen as the heart of the DA function.
        It is a recursive function and outputs school_placements, a dictionary with schools as keys and a list of tuples
        as values, with each tuple = (student,priority score). It uses the three above function."""
        placements = DA_helper().students_apply(students, id_to_school,
                                                placements)
        if guaranteed_current_seat_bool:
            placements = DA_helper().remove_over_capacity_currentseatguarantee(
                schools, placements, id_to_student)
        else:
            placements = DA_helper().remove_over_capacity(
                schools, placements)
        match = DA_helper().get_placement(placements, id_to_student)
        schoolid_studid_map = match[0]
        studid_schoolid_map = DA_helper().get_studid_schoolid_map(schoolid_studid_map)
        DA_helper().update_student_preliminary_placement_attribute(
            students, studid_schoolid_map)

        placed_students = match[1]
        i += 1

        nr_not_placed = 0
        for student in students:
            if student not in placed_students:
                nr_not_placed += 1

        if DA_helper().boolean_all_students_placed(students, placed_students):
            print('All students placed after round ', i)
            return schoolid_studid_map
        else:
            return self.DA_recursive(students, schools, id_to_school, id_to_student, placements, guaranteed_current_seat_bool, i)

    def run_DA(self, students: List[Student], schools: List[School], guaranteed_current_seat_bool: bool) -> list:
        """The main function that is called upon.
        This is the Gale-Shapley algorithm -- for school choice the Student Optimal Stable Mechanism or Student-Proposing Deferred Acceptance.
        For the algorithm to run correctly, capacities must be greater than number of students. If not, the algorithm will eventually break and
        output a list of unassigned students."""
        placements = DA_helper().create_placement_dict(schools)
        i = 0
        id_to_student = {student.participantid: student for student in students}
        id_to_school = {school.spgid: school for school in schools}
        schoolid_students_map = self.DA_recursive(
            students, schools, id_to_school, id_to_student, placements, guaranteed_current_seat_bool, i)
        studid_schoolid_map = DA_helper().get_studid_schoolid_map(schoolid_students_map)
        schools_except_outside = schools
        DA_helper().update_student_placement_attribute(
            students, schools_except_outside, studid_schoolid_map)
        DA_helper().update_school_available_seats(
            schools_except_outside, schoolid_students_map)
        DA_helper().update_school_cutoff(schools_except_outside, schoolid_students_map)

        print('DA algorithm terminated: students successfully matched to schools.')
        return students, schools_except_outside
