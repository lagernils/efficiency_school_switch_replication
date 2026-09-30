
from functions.get_data import Student, School, PlacementRound
from datetime import datetime, date

class Get_Stats:
    def get(self, all_students: list[Student], all_schools: list[School], final_placement_date=None) -> dict:
        nr_switchers = self.get_nr_switchers(all_students)
        nr_first_preference_switchers = self.get_nr_first_preference_switchers(all_students)
        avg_waiting_time_total = 0  # Placeholder for average waiting time computation
        avg_waiting_time_switchers = 0  # Placeholder for average waiting time for switchers
        all_schools = self.get_placed_students(all_students, all_schools)
        all_schools = self.get_school_cutoffs(all_schools)
        nr_blocking_pairs, nr_students_with_a_blocking_pair = self.get_nr_blocking_pairs(all_students, all_schools)  # Placeholder for number of blocking pairs computation
        total_waiting_time_dict = self.get_total_waiting_time(all_students, final_placement_date)
        total_waiting_time = total_waiting_time_dict['total_waiting_time']
        total_waiting_time_switchers = total_waiting_time_dict['total_waiting_time_switchers']
        avg_waiting_time_total = total_waiting_time / len(all_students) if len(all_students) > 0 else 0
        avg_waiting_time_switchers = total_waiting_time_switchers / nr_switchers if nr_switchers > 0 else 0
        price_switch_by_BP = nr_blocking_pairs / nr_switchers if nr_switchers > 0 else 0
        stats = {
            'total_nr_students': len(all_students),
            'nr_switchers': nr_switchers,
            'nr_first_preference_switchers': nr_first_preference_switchers,
            'percent_switchers': round((nr_switchers / len(all_students)) * 100, 2) if len(all_students) > 0 else 0,
            'percent_first_preference_switchers': round((nr_first_preference_switchers / len(all_students)) * 100, 2) if len(all_students) > 0 else 0,
            'nr_blocking_pairs': nr_blocking_pairs,
            'nr_students_with_a_blocking_pair': nr_students_with_a_blocking_pair,
            'avg_waiting_time_total': round(avg_waiting_time_total, 2),
            'avg_waiting_time_switchers': round(avg_waiting_time_switchers, 2),
            'total_waiting_time': total_waiting_time,
            'total_waiting_time_switchers': total_waiting_time_switchers,
            'price_switch_by_BP': round(price_switch_by_BP, 2)
        }
        # optionally, include total waiting time in stats
        #stats['total_waiting_time_days'] = total_waiting_time
        return stats
    
    def get_nr_switchers(self, all_students: list[Student]) -> int:
        return len([student for student in all_students if student.placement_date not in (None, '')])
    
    def get_nr_first_preference_switchers(self, all_students: list[Student]) -> int:
        count = 0
        for student in all_students:
            for spgid, placement_bool in student.documentation_placement.items():
                if placement_bool and spgid != student.current_school_spg:
                    if spgid == student.complete_preferences[0]:
                        count += 1
        return count
    
    def get_placed_students(self, students: list[Student], all_schools: list[School]) -> list[School]:
        spgid_to_school = {school.spgid: school for school in all_schools}
        for student in students:
            #print(f'Student {student.participantid} documentation_placement: {student.documentation_placement}')
            if student.current_school_spg not in student.documentation_placement:
                print(f'Warning: Student {student.participantid} current school not in documentation_placement keys')
                for attribute in vars(student):
                    print(f'  {attribute}: {getattr(student, attribute)}')
            if not student.documentation_placement[student.current_school_spg]:
                for spgid, placement_bool in student.documentation_placement.items():
                    if placement_bool:
                        school = spgid_to_school[spgid]
                        if student not in school.placed_studentobjs:
                            school.placed_studentobjs.append(student)
        return all_schools
    
    def get_school_cutoffs(self, all_schools: list[School]) -> list[School]:
        for school in all_schools:
            placed_students = school.placed_studentobjs
            # sort by priority score, lowest priority score is first in list
            placed_students_sorted = sorted(placed_students, key=lambda student: student.prio_score[school.spgid])
            prios_placed_students_sorted = [student.prio_score[school.spgid] for student in placed_students_sorted]
            # if list is empty, cutoff is 0
            if not prios_placed_students_sorted:
                school.cutoff = 0
                continue
            marginal_prio = max(prios_placed_students_sorted)
            school.cutoff = marginal_prio
        return all_schools

    def get_nr_blocking_pairs(self, all_students: list[Student], all_schools: list[School]) -> int:
        """Count blocking pairs.

        For each student, walk their `complete_preferences` in order. For each
        preferred `spgid` until the school they are placed at, count one
        blocking pair whenever the student's `prio_score[spgid]` is strictly
        better (smaller) than the school's `cutoff`.
        """
        nr_blocking_pairs = 0
        students_with_a_blocking_pair = []
        spgid_to_school = {school.spgid: school for school in all_schools}

        for student in all_students:
            # iterate preferences from most- to least-preferred; stop when we
            # reach the school the student is actually placed at
            for spgid in student.complete_preferences:
                placed_here = student.documentation_placement.get(spgid, False)
                if placed_here:
                    # reached the school where the student is placed; move to next student
                    break
                cutoff = spgid_to_school[spgid].cutoff
                prio = student.prio_score[spgid]
                if prio < cutoff:
                    nr_blocking_pairs += 1
                    if student.participantid not in students_with_a_blocking_pair:
                        students_with_a_blocking_pair.append(student.participantid)
                    #print(f'Blocking pair: Student {student.participantid} (prio {prio}) and School {spgid} (cutoff {cutoff})')
        # raise ValueError if any blocking pairs were found
        #if nr_blocking_pairs > 0:
            #print(f'Warning: Found {nr_blocking_pairs} blocking pairs in total.')
            #raise ValueError(f'Found {nr_blocking_pairs} blocking pairs in total.')
        
        return nr_blocking_pairs, len(students_with_a_blocking_pair)
        
    def get_total_waiting_time(self, all_students: list[Student], final_placement_date=None) -> int:
        """Compute total waiting time in days for all students."""

        # determine program end date (prefer supplied final_placement_date)
        last_date = self._pd(final_placement_date) if final_placement_date else None
        if last_date is None:
            placed = [self._pd(s.placement_date) for s in all_students if s.placement_date not in (None, "")]
            last_date = max(placed) if placed else None

        total = 0
        total_among_switchers = 0
        for s in all_students:
            application_day = self._pd(getattr(s, 'application_date_randomised', None))
            if application_day is None:
                continue
            is_switcher = s.placement_date not in (None, "")
            placement_day = self._pd(s.placement_date) if is_switcher else last_date
            if placement_day is None:
                continue
            days = max((placement_day - application_day).days, 0)
            total += days
            # Switcher classification is `placement_date != ""`. The previous
            # `placement_day != last_date` guard here dropped any switcher whose
            # placement-round end happened to coincide with the year's final
            # date (i.e. all switchers when k = 365), biasing this stat down.
            if is_switcher:
                total_among_switchers += days
        return {'total_waiting_time': total, 'total_waiting_time_switchers': total_among_switchers}


    def _pd(self,x) -> date | None:
        if not x:
            return None
        if isinstance(x, datetime):
            return x.date()
        if isinstance(x, date):
            return x
        s = str(x)
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            raise ValueError(f"Unrecognized date format: {x}")