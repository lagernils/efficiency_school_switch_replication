from typing import List, Tuple
from functions.get_data import School
from functions.get_data import Student
from .EADAM_helper import EADAM_helper


class EADAM():

    def run(self, students: List[Student], schools: List[School]) -> Tuple[List[Student], List[School]]:
        """The main function that is called upon.
        This is Fast EADAM (Simplified EADAM, Tang & Yu 2014), which produces the same
        assignment as Kesten's (2010) Efficiency-Adjusted Deferred Acceptance but with
        far fewer DA re-runs. When every student consents (student.consent == 1), the
        output is the Student-Optimal Legal Assignment. When no student consents
        (student.consent == 0 for all), the output equals student-proposing DA.

        EADAM operates on a per-student working copy `student.eadam_preferences` so
        the original `complete_preferences` is preserved for downstream welfare
        analysis."""
        # Initialize the working preference list from the (bounce-back-extended) originals.
        for student in students:
            student.eadam_preferences = list(student.complete_preferences)

        # Each non-terminating pass strictly shortens at least one student's
        # working preference list, so the number of passes is bounded by the
        # total number of preference entries. Stating the bound explicitly is
        # defensive: it turns a capacity vector the underdemand test cannot
        # resolve into a fast, loud failure instead of a silent infinite loop.
        max_passes = sum(len(s.complete_preferences) for s in students) + 2
        i = 0
        for _ in range(max_passes):
            i += 1
            match, proposers = EADAM_helper().run_inner_DA(students, schools)
            underdemanded = EADAM_helper().get_essentially_underdemanded(schools, proposers)
            if len(underdemanded) == len(schools):
                break
            EADAM_helper().fix_matched_at_underdemanded(students, schools, underdemanded, match)
            EADAM_helper().clear_unmatched_students(students, schools, match)
        else:
            raise RuntimeError(
                f"EADAM failed to converge after {max_passes} passes: the "
                f"essentially-underdemanded set never grew to all {len(schools)} "
                "schools. This means the capacity vector contains a school the "
                "underdemand test cannot resolve."
            )

        # Apply final match to student / school attributes (mirror DA_helper).
        EADAM_helper().update_student_placement_attribute(students, schools, match)
        EADAM_helper().update_school_available_seats(schools, match)
        EADAM_helper().update_school_cutoff(students, schools, match)

        print(f'EADAM algorithm terminated after {i} DA re-run(s): students successfully matched to schools.')
        return students, schools
