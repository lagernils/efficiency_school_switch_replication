from functions.EADAM_impl.EADAM import EADAM
from functions.update_round import Update_Round
from functions.main_helper import Helper


class Dynamic_EADAM():

    def run(self, grade, grade_to_pr_to_students, grade_to_pr_to_schools, list_of_adapted_rounds, base_capacity, test_mode, extra_seats=None) -> None:
        """Run the Dynamic EADAM algorithm for a given grade across multiple placement rounds."""

        students_without_placement = []
        students_with_placement = []
        prid_to_pr = {pr.id: pr for pr in list_of_adapted_rounds}
        for pr in grade_to_pr_to_students[grade]:
            students = grade_to_pr_to_students[grade][pr]
            schools = grade_to_pr_to_schools[grade][pr]
            for student in students_without_placement:  # Carry over unplaced students
                if student not in students:
                    students.append(student)
            for student in students:
                student.application_history = []
                student.preliminary_placed = False
                student.documentation_placement = {}
                student.documentation_application_history = []
                student.placement = {}
                student.placement_date = ''
                student.last_pr_as_participant = pr
                student.eadam_preferences = []

            print(f"Running EADAM for Placement Round ID {pr} for Grade {grade}...")
            schools = Update_Round().update_school_capacities(students, schools, students_without_placement, students_with_placement, base_capacity, extra_seats)

            students, schools = EADAM().run(students, schools)

            students = Update_Round().update_placement_documentation(students)
            students_without_placement = Update_Round().get_students_without_placement(students, schools)
            students_with_placement_for_this_round = [s for s in students if s not in students_without_placement]
            # EADAM Pareto-improves on DA; use the same (weak) efficiency check as TTC.
            Update_Round().verify_Pareto_efficiency(students_without_placement, students_with_placement_for_this_round, schools)
            placement_round_obj = prid_to_pr[pr]
            students_with_placement_for_this_round = Update_Round().add_placement_info(students_with_placement_for_this_round, placement_round_obj)
            students_with_placement = students_with_placement + students_with_placement_for_this_round
            if test_mode:
                Helper().print_placements(students_with_placement_for_this_round, students_with_placement, students_without_placement)
