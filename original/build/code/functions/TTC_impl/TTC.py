# Adapted from Luke Carani's matching-algorithms
# (https://github.com/lwcarani/matching-algorithms), with thanks, and modified
# substantially for the capacity-constrained school-switch setting. That
# repository carries no licence, so these files are not covered by the MIT
# licence at the repository root. Any remaining errors are our own.

from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from .graph import Graph
from .TTC_helper import find_all_cycles, update_graph
from functions.get_data import Student, School


class TTC:
    """Thin wrapper around `algos.top_trading_cycle.ttc`.

    See `run()` for full documentation and examples.
    """

    def run(self, students: List[Student], schools: List[School]) -> Dict[str, object]:
        """Run the Top Trading Cycle (TTC) algorithm and returns updated students and schools. """
        
        # Build school capacity dict
        schools_with_capacity = [school for school in schools if school.capacity > 0]
        school_capacities = {school.spgid: school.capacity for school in schools_with_capacity}

        # Build student preferences dict
        student_preferences = self.get_student_preferences(students, schools_with_capacity)

        # Build school priorities dict
        school_priorities = self.get_school_priorities(students, schools_with_capacity)

        match = self.get_ttc_match(
            student_preferences = student_preferences, 
            school_preferences = school_priorities, 
            school_capacities = school_capacities, 
            round_callback=None
        )

        
        students = self.update_student_placements(students, schools, match)
        #self.print_matches(students)
        schools = self.update_school_cutoffs(students, schools)

        return students, schools
    
    def get_student_preferences(self, students: List[Student], schools_with_capacity: List[School]) -> Dict[str, List[str]]:
        """Build student preferences dict from students' complete_preferences.

        Returns Dict with student preferences (Dict[str, List[str]]): mapping
        student id -> list of school ids in strict preference order (index 0 ==
        most preferred). Example: {"i1": ["sA", "sB"], "i2": ["sB", "sA"]}.
        """
        student_preferences = {}
        for student in students:
            complete_preferences_for_schools_with_capacity = [spgid for spgid in student.complete_preferences if spgid in {school.spgid for school in schools_with_capacity}]
            student_preferences[student.participantid] = complete_preferences_for_schools_with_capacity
        return student_preferences
    
    def get_school_priorities(self, students: List[Student], schools: List[School]) -> Dict[str, List[str]]:
        """Build school priorities dict from students' priority scores.

        Returns Dict with school priorities (Dict[str, List[str]]): mapping
        school id -> list of student ids in strict priority order (index 0 ==
        highest priority). Example: {"sA": ["i2", "i1"], "sB": ["i1", "i2"]}.
        """
        school_priorities = {}
        for school in schools:
            priority_list = []
            for student in students:
                priority_list.append((student.participantid, student.prio_score[school.spgid]))
            # sort by priority score, lowest score is highest priority
            priority_list_sorted = sorted(priority_list, key=lambda x: x[1])
            school_priorities[school.spgid] = [student_id_prio_tuple[0] for student_id_prio_tuple in priority_list_sorted]
        return school_priorities
    
    def print_matches(self, students: List[Student]):
        """Print the TTC matches."""
        print("TTC Matches:")
        for student in students:
            for spgid, placed in student.placement.items():
                if placed:
                    if student.current_school_spg == spgid:
                        print(f"Student {student.participantid} remains at current school {spgid}.")
                    else:
                        print(f"Student {student.participantid} assigned to new school {spgid}.")
    
    def update_student_placements(self, students: List[Student], schools: List[School], match: Dict[str, str]) -> List[Student]:
        """Update student.placement attribute based on TTC match."""
        for student in students:
            assigned_school_spgid = match.get(student.participantid)
            for school in schools:
                student.placement[school.spgid] = (assigned_school_spgid == school.spgid)
        return students
    
    def update_school_cutoffs(self, students: List[Student], schools: List[School]) -> List[School]:
        """Update school.cutoff attribute based on TTC placements."""
        for school in schools:
            placed_students = [student for student in students if student.placement.get(school.spgid, False)]
            # sort by priority score, lowest priority score is first in list
            placed_students_sorted = sorted(placed_students, key=lambda student: student.prio_score[school.spgid])
            prios_placed_students_sorted = [student.prio_score[school.spgid] for student in placed_students_sorted]
            if not prios_placed_students_sorted: # if list is empty, cutoff is 0
                school.cutoff = 0
                continue
            school.cutoff = max(prios_placed_students_sorted) # highest priority score among placed students
        return schools

    def get_ttc_match(self, student_preferences: Dict[str, List[str]], school_preferences: Dict[str, List[str]], school_capacities: Dict[str, int] | None = None, round_callback=None) -> Dict[str, List[str]]:
        """Run the Top Trading Cycle (TTC) algorithm. 
        Originally developed by David Gale. Published in Shapley and Scarf (1974). 
        Adapted for school choice implementation in Abdulkadiroğlu and Sönmez (2003).
        Credit to Luke Carani for source code. See https://github.com/lwcarani/matching-algorithms.
        
        Parameters
        - student_preferences Dict[str, List[str]]: mapping student id -> list of school ids in strict preference order (index 0 == most preferred). 
        Example: {"i1": ["sA", "sB"], "i2": ["sB", "sA"]}.

        - school_priorities Dict[str, List[str]]: mapping school id -> list of student ids in strict priority order (index 0 == best prio). 
        Example: {"sA": ["i2", "i1"], "sB": ["i1", "i2"]}.

        - school_capacities [Dict[str, int]]: mapping school id -> integer capacity (>= 0). 
        Example: {"sA": 2, "sB": 1}.

        - round_callback (optional callable): forwarded to the underlying
          TTC implementation. Expected signature similar to
          `round_callback(round_number, cycles, matches_made, capacities)`.

        Returns Dict with matches (Dict[str, str]): mapping student id -> assigned
          school id. Unmatched students (if any) are represented as
          `student: student` (value equals key), preserving the existing TTC
          return convention. 
          Example: {"i1": "sB", "i2": "sA", "i3": "i3"}.
        """
        
        matches: Dict[str, str] = {}
        students = set(student_preferences.keys())
        schools = set(school_preferences.keys())
        all_nodes = students | schools

        # instantiate a new Graph object with all employee and job nodes
        # initially, this graph will only have nodes, no edges
        G = Graph(all_nodes)

        # queue (counter) to track which school we are currently considering for the current student
        # i.e., if school_index is 2, then we are considering the 3rd school on the given
        school_queue: Dict = defaultdict(int)
        student_queue: Dict = defaultdict(int)

        # capacities: remaining seats per school
        c = dict(school_capacities)

        # Remaining schools are those with c[s] > 0
        remaining_schools = {s for s, cap in c.items() if cap > 0}

        # map school -> list of assigned students (for reverse mapping)
        school_assignments: Dict[str, List[str]] = defaultdict(list)

        # add edges to build out graph using remaining_schools / remaining students
        for i in students:
            # point to top ranked remaining school
            for idx, sc in enumerate(student_preferences[i][school_queue[i] :], start=school_queue[i]):
                if sc in remaining_schools:
                    school_queue[i] = idx
                    G.add_edge(i, sc)
                    break
        for sc in list(remaining_schools):
            # school points to best remaining student according to its priority list
            for st in school_preferences[sc]:
                if st in students:
                    G.add_edge(sc, st)
                    break

        # Remove top trading cycles until graph is empty
        round_number = 0
        while G.number_of_nodes_in_graph() > 0:
            # find all cycles in the graph snapshot for this round
            cycles = find_all_cycles(G)

            # make assignments of students to school based on all cycles found this round
            round_number += 1
            # collect schools touched in these cycles so we can check capacities after
            schools_in_cycle = set()
            matches_made = []
            for cycle in cycles:
                for node in cycle:
                    if node in students:
                        school: str = G.nodes[node].get_next_node()
                        matches[node] = school
                        school_assignments[school].append(node)
                        schools_in_cycle.add(school)
                        matches_made.append((node, school))
                        # remove the student from graph (they're assigned)
                        G.delete_node(node)

            # debug prints: show cycles found and matches made this round
            #print(f"TTC round {round_number}: cycles={cycles}")
            #print(f"TTC round {round_number}: matches_made={matches_made}")

            # decrement capacities for each school in the cycle equal to number of assigned students in this step
            for sc in schools_in_cycle:
                # decrement once per student assigned to sc in this cycle
                # (in TTC cycles schools appear at most once per cycle)
                c[sc] -= 1
                if c[sc] <= 0:
                    # remove school from remaining and from graph
                    if sc in G.nodes:
                        G.delete_node(sc)
                    remaining_schools.discard(sc)

            # callback with round info if provided
            if round_callback is not None:
                try:
                    # pass all cycles discovered this round and matches made
                    round_callback(round_number, cycles, matches_made, dict(c))
                except Exception:
                    # don't let callback errors break algorithm
                    pass

            # update the graph with new edges after cycle was found and matches were made
            G, matches, student_queue, school_queue, c, remaining_schools = update_graph(
                G,
                matches,
                student_preferences,
                school_preferences,
                student_queue,
                school_queue,
                c,
                remaining_schools,
            )

        # return student->school mapping. If a student is unmatched, they map to themselves.
        return {student: matches[student] for student in students}



if __name__ == "__main__":
    # simple runnable example using the docstring example
    student_preferences = {
        "i1": ["sA", "sB", "sC"],
        "i2": ["sA", "sB", "sC"],
        "i3": ["sB", "sA", "sC"],
    }

    school_preferences = {
        "sA": ["i2", "i1", "i3"],
        "sB": ["i3", "i1", "i2"],
        "sC": ["i1", "i2", "i3"],
    }

    capacities = {"sA": 1, "sB": 1, "sC": 1}

    matches = TTC().run(student_preferences, school_preferences, capacities)
    print("One-sided (student->school):", matches["one_sided"])
    print("Two-sided (school->assigned):", matches["two_sided"])
