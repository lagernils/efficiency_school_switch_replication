from functions.TTC_impl.TTC import TTC
from functions.update_round import Update_Round
from functions.main_helper import Helper


class Dynamic_TTC():

    def run(self, grade, grade_to_pr_to_students, grade_to_pr_to_schools, list_of_adapted_rounds, base_capacity, test_mode, extra_seats=None) -> None:
        """Run the Dynamic Top Trading Cycles algorithm for a given grade across multiple placement rounds."""

        students_without_placement = []
        students_with_placement = []
        prid_to_pr = {pr.id: pr for pr in list_of_adapted_rounds}
        for pr in grade_to_pr_to_students[grade]:
            students = grade_to_pr_to_students[grade][pr]
            schools = grade_to_pr_to_schools[grade][pr]
            for student in students_without_placement: # Carry over unplaced students
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

            print(f"Running TTC for Placement Round ID {pr} for Grade {grade}...")
            #print(f"Number of students before TTC: {len(students)}")
            schools = Update_Round().update_school_capacities(students, schools, students_without_placement, students_with_placement, base_capacity, extra_seats)
            #print(f"School capacities after update for Placement Round ID {pr}:")
            #print(sum(school.capacity for school in schools))

            students, schools = TTC().run(students, schools)

            students = Update_Round().update_placement_documentation(students)
            students_without_placement = Update_Round().get_students_without_placement(students, schools)
            students_with_placement_for_this_round = [s for s in students if s not in students_without_placement]
            #Update_Round().verify_optimal_stable(students_without_placement,students_with_placement_for_this_round, schools)
            Update_Round().verify_Pareto_efficiency(students_without_placement,students_with_placement_for_this_round, schools)
            placement_round_obj = prid_to_pr[pr]
            students_with_placement_for_this_round = Update_Round().add_placement_info(students_with_placement_for_this_round, placement_round_obj)
            students_with_placement = students_with_placement  + students_with_placement_for_this_round
            #print(f"Total nr of students with placement for grade {grade} after Placement Round ID {pr}: {len(students_with_placement)}")
            #print(f"Number of students without placement: {len(students_without_placement)}")
            if test_mode:
                Helper().print_placements(students_with_placement_for_this_round, students_with_placement, students_without_placement)