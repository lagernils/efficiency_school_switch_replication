from typing import List
import heapq
from functions.get_data import School
from functions.get_data import Student


class DA_helper:

    def create_placement_dict(self, schools: List[School]):
        """Creates a placement dict with every school-id as key and empty lists as values."""
        placements = {}
        for school in schools:
            placements[school.spgid] = []
        return placements

    def get_updated_preference_list(self, student: Student):
        """For a given student, this function returns the schools to which the student haven't already applied to in earlier DA rounds."""
        schools_already_applied_to = set(student.application_history)
        updated_preferences = [spgid for spgid in student.complete_preferences if spgid not in schools_already_applied_to]
        return updated_preferences

    def apply_to_top_school(self, student: Student, id_to_school, placements):
        """Students apply to schools by adding themselves to the list of placement[school.spgid]"""
        schools_already_applied_to = set(student.application_history)
        top_school_id = None
        for spgid in student.complete_preferences:
            if spgid not in schools_already_applied_to:
                top_school_id = spgid
                break

        if top_school_id is not None:
            student_prio_tuple = (student.participantid, student.prio_score[top_school_id])
            placements[top_school_id].append(student_prio_tuple)
            student.application_history.append(top_school_id)
        return placements

    def students_apply(self, students: List[Student], id_to_school, placements):
        """Students apply to schools if not preliminary placed in the DA algorithm."""
        for student in students:
            if student.preliminary_placed == False:
                placements = self.apply_to_top_school(student, id_to_school, placements)
        return placements

    def remove_over_capacity(self, schools: List[School], placements):
        """Efficiently enforce capacity limits on school applicant lists."""
        for school in schools:
            if school.capacity <= 0:
                placements[school.spgid] = []
                continue
            applicants = placements[school.spgid]
            if len(applicants) > school.capacity:
                best_k = heapq.nsmallest(school.capacity, applicants, key=lambda a: a[1])
                placements[school.spgid] = best_k

        return placements

    def remove_over_capacity_currentseatguarantee(self, schools: List[School], placements, id_to_student):
        """Sorts students based on priority score and ejects all students with priority over the (capacity-induced) cutoff."""
        for school in schools:
            current_students = self.get_current_students(school, placements[school.spgid], id_to_student)

            placements[school.spgid].sort(key=lambda a: a[1])
            placements[school.spgid] = placements[school.spgid][:school.capacity]

            for student in current_students:
                student_tuple = (student.participantid, student.prio_score[school.spgid])
                if student_tuple not in placements[school.spgid]:
                    placements[school.spgid].append(student_tuple)
        return placements

    def get_current_students(self, school: School, all_students, id_to_student):
        current_students = []
        for student_tuple in all_students:
            student = id_to_student[student_tuple[0]]
            if student.current_school_spg == school.spgid:
                current_students.append(student)
        current_students.sort(key=lambda student: student.prio_score[school.spgid])
        return current_students

    def get_placement(self, placements, id_to_student):
        """Returns mu^{-1} function (mapping of schools to students) and a list of placed students"""
        placed_students = []
        school_stud_map = {}
        for schoolid in placements:
            school_stud_map[schoolid] = []
            for student_tuple in placements[schoolid]:
                studentid = student_tuple[0]
                student = id_to_student[studentid]
                placed_students.append(student)
                school_stud_map[schoolid].append(student)
        return school_stud_map, placed_students

    def boolean_all_students_placed(self, students: List[Student], placed_students):
        """Boolean function indicating if all students are placed."""
        return len(placed_students) == len(students)

    def update_student_preliminary_placement_attribute(self, students: List[Student], studid_schoolid_map):
        """Updates attribute preliminary_placement under a given DA round."""
        for student in students:
            student.preliminary_placed = (student.participantid in studid_schoolid_map)

    def get_studid_schoolid_map(self, school_stud_map):
        """Returns mu function, i.e. the mapping of student.participantid to their placement: school.spgid"""
        studid_schoolid_map = {}
        for schoolid in school_stud_map:
            for student in school_stud_map[schoolid]:
                studid_schoolid_map[student.participantid] = schoolid
        return studid_schoolid_map

    def update_student_placement_attribute(self, students: List[Student], schools: List[School], studid_schoolid_map: dict):
        """Updates placement attribute after DA placement"""
        for student in students:
            placed_spgid = studid_schoolid_map.get(student.participantid)
            for school in schools:
                student.placement[school.spgid] = (school.spgid == placed_spgid)

    def update_school_available_seats(self, schools: List[School], schoolid_students_map):
        """Updates available seats attribute after DA placement."""
        for school in schools:
            if school.spgid in schoolid_students_map:
                school.available_seats = school.capacity - len(schoolid_students_map[school.spgid])
            else:
                school.available_seats = school.capacity

    def update_school_cutoff(self, schools: List[School], schoolid_students_map):
        """Updates cutoff attribute after DA placement."""
        for school in schools:
            placed_students = schoolid_students_map.get(school.spgid, [])
            if len(placed_students) == school.capacity:
                if placed_students:
                    school.cutoff = max(student.prio_score[school.spgid] for student in placed_students)
                else:
                    school.cutoff = 0
            else:
                school.cutoff = 1000000
