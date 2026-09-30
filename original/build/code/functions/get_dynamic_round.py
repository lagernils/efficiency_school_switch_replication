"""Generate dynamic rounds placeholder.

This module provides a small class with a `get` entrypoint that accepts
`students`, `schools`, and `adapted_rounds` and returns the (possibly
modified) `students` and `schools` back. The current implementation is a
no-op and can be extended with domain logic later.
"""

from typing import Tuple
import copy
from copy import deepcopy
from functions.get_data import Student, School


class Generate_Dynamic_Round:
    """Generate or modify rounds dynamically from data.

    The `get` method is designed to be called from `main.py` after
    `adapted_rounds` are created. It returns the (students, schools)
    pair so it can mutate structures in-place or produce replacements.
    """

    def get(self, students: list[Student], schools: list[School], adapted_rounds, random_priorities: bool = False) -> dict:
        """Process inputs and return (students, schools).

        Current behaviour: no-op, returns inputs unchanged.
        """
        # Placeholder: implement dynamic round generation or student/school
        # adjustments here.
        self.students = students
        self.schools = schools
        self.adapted_rounds = adapted_rounds
        self.random_priorities = random_priorities

        ### Get relevant dicts (prep work) ###
        self.year_grade_to_spgs = self.get_year_grade_to_spgs()
        self.year_grade_to_students = self.get_year_grade_to_students()
        self.year_grade_to_pr_to_students = self.initialise_year_grade_to_pr_to_students()

        ### Update students and schools ###
        self.update_adapted_round()
        self.update_studentdicts_for_applicable_spgs()
        self.update_priogroup_to_current_school()
        self.update_prioscores()
        self.year_grade_to_pr_to_schools = self.get_year_grade_to_pr_to_schools()
        self.update_current_students_at_school()
        self.update_student_preferences()
        
        return {'students': self.students, 
                'schools': self.schools, 
                'year_grade_to_pr_to_students': self.year_grade_to_pr_to_students, 
                'year_grade_to_pr_to_schools': self.year_grade_to_pr_to_schools}
    
    ### PREP WORK ###
        
    def get_year_grade_to_spgs(self) -> dict:
        """Get mapping from year and grade to list of spgids."""
        year_grade_to_spgs = {}
        for school in self.schools:
            if school.year not in year_grade_to_spgs:
                year_grade_to_spgs[school.year] = {}
            if school.grade not in year_grade_to_spgs[school.year]:
                year_grade_to_spgs[school.year][school.grade] = []
            year_grade_to_spgs[school.year][school.grade].append(school.spgid)
        return year_grade_to_spgs
    
    def get_year_grade_to_students(self) -> dict:
        """Get mapping from year and grade to list of students."""
        year_grade_to_students = {}
        for year in self.adapted_rounds:
            year_grade_to_students[year] = {}
            for grade in self.adapted_rounds[year]:
                year_grade_to_students[year][grade] = []
        for student in self.students:
            student.year = self.get_year(student.application_date_randomised)
            if student.year not in year_grade_to_students:
                continue
            year_grade_to_students[student.year][student.grade].append(student)
        self.students = [s for s in self.students if s.year in year_grade_to_students]
        return year_grade_to_students
    
    def get_year(self, date_str) -> int:
        """Get academic year from date string."""
        # if eg date is between 2021-06-30 and 2022-06-29, year is 2021
        year = int(date_str.split('/')[0])
        month = int(date_str.split('/')[1])
        day = int(date_str.split('/')[2])
        if month >= 7 or (month == 6 and day >= 30):
            return year
        else:
            return year - 1
    
    def initialise_year_grade_to_pr_to_students(self) -> dict:
        """Initialise mapping from year and grade and adapted placementroundid to list of students."""
        year_grade_to_pr_to_students = {}
        for year, grade_to_prs_dict in self.adapted_rounds.items():
            year_grade_to_pr_to_students[year] = {}
            #print(f"Dynamic Round Generation - Grade {grade}: {len(self.adapted_rounds[grade])} adapted rounds")
            for grade, placementrounds in grade_to_prs_dict.items():
                year_grade_to_pr_to_students[year][grade] = {}
                for placementround in placementrounds:
                    year_grade_to_pr_to_students[year][grade][placementround.id] = []
                #print(f"  ID: {ar.id}, Start: {ar.application_start}, End: {ar.application_end}")
        return year_grade_to_pr_to_students
    
    def get_year_grade_to_pr_to_schools(self) -> dict:
        """Get mapping from year and grade to adapted placementroundid to list of schools."""
        #spg_to_school_dict = {school.spgid: school for school in self.schools}
        year_grade_to_pr_to_schools = {}
        for year in self.adapted_rounds:
            spg_to_school_dict = {school.spgid: school for school in self.schools if school.year == year}
            year_grade_to_pr_to_schools[year] = {}
            for grade in self.year_grade_to_spgs[year]:
                year_grade_to_pr_to_schools[year][grade] = {}
                spgs = self.year_grade_to_spgs[year][grade]
                for spgid in spgs:
                    school = spg_to_school_dict[spgid]
                    for adapted_round in self.adapted_rounds[year][grade]:
                        if adapted_round.id not in year_grade_to_pr_to_schools[year][grade]:
                            year_grade_to_pr_to_schools[year][grade][adapted_round.id] = []
                        year_grade_to_pr_to_schools[year][grade][adapted_round.id].append(school)

        return year_grade_to_pr_to_schools
    
    ### UPDATES ###
    
    def update_adapted_round(self) -> None:
        """Update adapted rounds based on student application dates and applicable_spgs.
        Assign each student to the correct adapted round based on their application date.
        Ensure adapted round's applicable_spgs is the intersection of all students' applicable_spgs.
        Ensure each student's applicable_spgs is consistent with the adapted round's applicable_spgs."""
        for student in self.students:
            #student_year = self.get_year(student.application_date_randomised)
            for adapted_round in self.adapted_rounds[student.year][student.grade]:
                if student.application_date_randomised <= adapted_round.application_end and student.application_date_randomised >= adapted_round.application_start:
                    student.placementround = adapted_round.id
                    if student.current_school_spg is not None:
                        self.year_grade_to_pr_to_students[student.year][student.grade][adapted_round.id].append(student) # Ignore students without current_school_spg
                    # update adapted round's list_of_raw_placementrounds and applicable_spgs
                    if student.placementround_raw not in adapted_round.list_of_raw_placementrounds:
                        adapted_round.list_of_raw_placementrounds.append(student.placementround_raw)
                    if adapted_round.applicable_spgs == []:
                        adapted_round.applicable_spgs = student.applicable_spgs
                    elif set(adapted_round.applicable_spgs).issubset(set(student.applicable_spgs)):
                        # adapted round applicable_spgs is a subset of student applicable_spgs
                        adapted_round.applicable_spgs = student.applicable_spgs
                        pass
                    elif set(student.applicable_spgs).issubset(set(adapted_round.applicable_spgs)):
                        # student applicable_spgs is a subset of adapted round applicable_spgs
                        student.applicable_spgs = adapted_round.applicable_spgs
                        pass
                    else:
                        merged = set(adapted_round.applicable_spgs) | set(student.applicable_spgs)
                        adapted_round.applicable_spgs = list(merged)
                        student.applicable_spgs = list(merged)
                    break
    
    def update_studentdicts_for_applicable_spgs(self) -> None:
        """Ensure that each student's dict attributes have entries for all applicable_spgs."""
        for student in self.students:
            for spgid in self.year_grade_to_spgs[student.year][student.grade]:
                if spgid not in student.preferences_dict:
                    student.preferences_dict[spgid] = None
                if spgid not in student.prioritygroup_dict:
                    student.prioritygroup_dict[spgid] = 1000000  # large default priority group
                if spgid not in student.distances_dict:
                    student.distances_dict[spgid] = 1000000  # large default distance
                if spgid not in student.relativedistances_dict:
                    student.relativedistances_dict[spgid] = 1000000  # large default relative distance
                if spgid not in student.prio_score:
                    student.prio_score[spgid] = None # to be updated later

    def update_priogroup_to_current_school(self) -> None:
        """Set prioritygroup_dict for each student at their current school to 0 (highest priority)."""
        for student in self.students:
            student.prioritygroup_dict[student.current_school_spg] = 0  # highest priority group for current school

    def update_prioscores(self) -> None:
        """Update prio_score for each student at each school based on priority group, relative distance, and lottery number.
        Current students (priority group 0) are ranked first by lottery number only.
        Other students are ranked by priority group (low to high), then relative distance (high to low), then lottery number (low to high)."""
        for year in self.year_grade_to_spgs:
            for grade in self.year_grade_to_spgs[year]:
                spgs = self.year_grade_to_spgs[year][grade]
                for spgid in spgs:
                    # Work on a copy to avoid mutating shared lists
                    students_copy = list(self.year_grade_to_students[year][grade])

                    # Split current students (priority group 0) and others
                    current_students = [s for s in students_copy if s.prioritygroup_dict[spgid] == 0]
                    other_students = [s for s in students_copy if s.prioritygroup_dict[spgid] != 0]

                    # Current students: tie-break by lottery only (low lottery number first)
                    current_students.sort(key=lambda s: s.lottery_number)

                    # Other students: priority group (low prio group first), then relative distance (high rd first), then lottery (low lottery first)
                    # If random_priorities is set, use single-tiebreaker lottery only.
                    other_students.sort(key=lambda s: s.lottery_number)
                    if not self.random_priorities:
                        other_students.sort(key=lambda s: s.relativedistances_dict.get(spgid, 0), reverse=True)
                        other_students.sort(key=lambda s: s.prioritygroup_dict.get(spgid, 1000000))

                    # Combine with current students first
                    ordered_students = current_students + other_students

                    # Assign prioscores based on sorted order
                    for idx, student in enumerate(ordered_students):
                        student.prio_score[spgid] = idx + 1  # 1-based index
    
    def update_current_students_at_school(self) -> None:
        """Update each school's current_students list based on students' current_school_spg."""
        for student in self.students:
            year_spg_to_school_dict = {school.spgid: school for school in self.schools if school.year == student.year}
            if student.current_school_spg in year_spg_to_school_dict:
                school = year_spg_to_school_dict[student.current_school_spg]
                if student.participantid not in school.current_students:
                    school.current_students.append(student.participantid)

    def update_student_preferences(self) -> None:
        """Update student preferences based their preferences_dict.
        ROL validity (spgid in this student's market) is enforced upstream
        in Get_Students.get_clean_students."""
        for student in self.students:
            pref_tuples = []
            for spgid in student.preferences_dict:
                pref_number = student.preferences_dict[spgid]
                if pref_number is not None:
                    pref_tuples.append((pref_number, spgid))
            pref_tuples.sort(key=lambda x: x[0]) # lower preference number first
            student.preferences = [spgid for (_, spgid) in pref_tuples]
            student.complete_preferences = copy.deepcopy(student.preferences)
            # add current_school_spg as last preference if not already present
            if student.current_school_spg not in student.preferences:
                student.complete_preferences.append(student.current_school_spg)