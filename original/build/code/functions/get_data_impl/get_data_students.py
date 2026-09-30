import pandas as pd
import random
from functions.get_data import Student
from typing import List, Tuple, Dict


# Seed of the iteration currently being run; set by main.Run_School_Switch.run_loop.
# Each student's lottery number is drawn from Random(f"{CURRENT_SEED}:{id}")
# rather than from the shared stream, so it depends only on the seed and the
# participant id -- not on how many numbers were drawn before it. That is what
# lets `original` and `replication_rr` produce identical lotteries.
CURRENT_SEED = 424242


class Get_Students():
    def __init__(self):
        # Initialize the students list which will be updated in-place by other methods
        self.students = []

    def get(self, pathnames, placementrounds, schools, unit_demand_mode, randomise_dates, municipality, full_consent_bool: bool = True) -> list[Student]:
        """Retrieve and return list of Student dataclass instances."""
        self.municipality = municipality
        self.full_consent_bool = full_consent_bool

        # Dict with placementround id to PlacementRound instance for easy lookup
        self.id_to_pr_dict = {pr.id: pr for pr in placementrounds}
        self.possible_application_dates = self._get_possible_application_dates(placementrounds)

        # dict of (schoolprogramid,grade) to spgid
        spgrade_to_spgid = {(school.spid, school.grade): school.spgid for school in schools}
        spgrade_to_spgid = self._add_legacy_spid_entries(spgrade_to_spgid, municipality)

        # Populate students from participants CSV
        self.get_csv_participants(pathnames["participants"], randomise_dates)

        # Update students in-place using mapping files per placement round
        self.get_csv_mappings(pathnames["mappings"], placementrounds, spgrade_to_spgid, unit_demand_mode)

        # Clean students in-place and return the final list
        self.get_clean_students(schools)
        return self.students
    
    def _get_possible_application_dates(self, placementrounds) -> dict:
        """Determine overall earliest and latest application dates from placement rounds."""
        earliest_dates = [pr.application_start for pr in placementrounds if pr.application_start is not None]
        latest_dates = [pr.application_end for pr in placementrounds if pr.application_end is not None]
        overall_earliest = min(earliest_dates) if earliest_dates else None
        overall_latest = max(latest_dates) if latest_dates else None
        return {'earliest': overall_earliest, 'latest': overall_latest}

    def get_csv_participants(self, pathname, randomise_dates) -> list[Student]:
        """Read participants CSV and return list of Student dataclass instances.

        Expected columns (used):
        - ParticipantId -> student.participantid
        - studentId -> student.studentid
        - placementRoundId -> student.placementround
        - choiceCreatedAt -> student.application_date
        - participantType -> student.type
        """
        df = pd.read_csv(pathname)
        self.students = []
        idx = 1
        for _, row in df.iterrows():
            idx = self._get_part_row(row, randomise_dates, idx)
        return self.students
        
    def get_csv_mappings(self, pathname, placementrounds, spgrade_to_spgid, unit_demand_mode) -> None:
        """Read mappings CSV and update Student objects (self.students) with additional data."""
        self.resolved_grades = self._resolve_multi_grade_students(pathname, placementrounds, spgrade_to_spgid)
        for pr in placementrounds:
            path = pathname + f"{pr.id}.csv"
            print(f"Reading student mappings for placement round {pr.id}")
            self.get_csv_mapping(path, spgrade_to_spgid, unit_demand_mode)
        
    def get_csv_mapping(self, path, spgrade_to_spgid, unit_demand_mode) -> None:
        df = pd.read_csv(path)
        spids_ignored = []
        # Build participantId -> Student mapping for easy lookup
        id_to_student = {student.participantid: student for student in self.students}
        for _, row in df.iterrows():
            self._get_map_row(row, id_to_student, spgrade_to_spgid, unit_demand_mode, spids_ignored)
        if spids_ignored:
            print(f"Warning: No spgid found for spids: {spids_ignored}")

    def _get_part_row(self, row, randomise_dates, idx) -> int:
        """Processes a row from the participants CSV and appends a Student object to self.students if applicable."""
        placementround = int(row['placementRoundId'])
        if placementround not in self.id_to_pr_dict:
            return idx # placement round filtered out earlier; skip
        application_date_raw = self._format_date(row.get('choiceCreatedAt'))
        application_date_random = self._get_random_application_date(application_date_raw, randomise_dates, placementround, row['ParticipantId'])
        lottery_number = random.Random(f"{CURRENT_SEED}:{row['ParticipantId']}").randint(1, 10000000)

        student = Student(
            idx = 0,
            participantid=str(row['ParticipantId']),
            studentid=str(row['studentId']),
            placementround_raw=placementround,
            placementround=0,  # to be updated later
            grade=None,
            type=row['participantType'],
            application_date=application_date_raw,
            application_date_randomised=application_date_random,
            year=0,
            lottery_number=lottery_number,
            applicable_spgs=[],
            preferences_dict={},
            preferences=[],
            complete_preferences=[],
            prioritygroup_dict={},
            distances_dict={},
            relativedistances_dict={},
            prio_score={},
            current_school_sp=row['switchingFromSchoolProgramId'],
            current_school_spg=None,
            application_history=[],
            placement={},
            preliminary_placed=False,
            last_pr_as_participant=0,
            placement_pr=0,
            placement_date='',
            documentation_placement={},
            documentation_application_history=[],
            consent=1 if self.full_consent_bool else 0,
            eadam_preferences=[],
        )
        self.students.append(student)
        return idx + 1

    def _get_map_row(self, row, id_to_student, spgrade_to_spgid, unit_demand_mode, spids_ignored) -> None:
        student = id_to_student.get(str(row['participantId']))
        if student is None:
            return # no matching student (maybe filtered out earlier); skip
        if pd.notna(row['grade']) and int(row['grade']) < 10:
            row_grade = int(row['grade'])
            if student.participantid in self.resolved_grades and row_grade != self.resolved_grades[student.participantid]:
                return
            student.grade = row_grade
            schoolprogramid = row.get('schoolProgramId')
            spgid_raw = spgrade_to_spgid.get((schoolprogramid, student.grade))
            if spgid_raw is None:
                if schoolprogramid not in spids_ignored: #ignore this spid and go to next row
                    spids_ignored.append(schoolprogramid)
                return
            spgid = spgid_raw
            if schoolprogramid == student.current_school_sp:
                student.current_school_spg = spgid
            # update student's dicts in-place
            if spgid not in student.applicable_spgs:
                student.applicable_spgs.append(spgid)
            student.prioritygroup_dict[spgid] = int(row['priorityGroup'])
            student.distances_dict[spgid] = float(row['distance'])
            student.relativedistances_dict[spgid] = float(row['relativeDistance'])
            if int(row['rankGroup']) == 1:
                if not unit_demand_mode:
                    student.preferences_dict[spgid] = int(row['ranking'])
                else:
                    student.preferences_dict[spgid] = 1 if int(row['ranking']) == 1 else None
            else:
                student.preferences_dict[spgid] = None

    def get_clean_students(self, schools) -> None:
        """Cleans the students list in-place by filtering out invalid entries and assigning indices.
        Drops preferences_dict entries whose (spgid, grade) does not appear in
        the schools list -- mirrors replication's data_loading.py:314 -- so
        students whose entire ROL points outside their market are removed by
        the existing _has_valid_preferences filter."""
        grade_to_spgids = {}
        for school in schools:
            grade_to_spgids.setdefault(school.grade, set()).add(school.spgid)
        for student in self.students:
            valid = grade_to_spgids.get(student.grade, set())
            for spgid in list(student.preferences_dict.keys()):
                if spgid not in valid:
                    del student.preferences_dict[spgid]
        self.students = [
            student for student in self.students
            if (student.grade is not None) # student has a grade
            and (student.current_school_sp is not None) and (student.current_school_spg is not None) # student has a current school spgid
            and (student.preferences_dict.get(student.current_school_spg) is None) # student not applying to current school
            and self._has_valid_preferences(student)
        ]
        for idx, student in enumerate(self.students, start=1):
            student.idx = idx
    
    def _has_valid_preferences(self, student) -> bool:
            prefs = student.preferences_dict
            if prefs == {}:
                return False
            return any(v is not None for v in prefs.values())
    
    def _resolve_multi_grade_students(self, pathname, placementrounds, spgrade_to_spgid) -> dict:
        """Pre-scan mapping files to find students with rows in multiple grades.
        For each, resolve the correct grade using current_school_sp from schools data.
        Returns dict of participantid -> resolved grade (only for multi-grade students)."""
        id_to_student = {student.participantid: student for student in self.students}
        participant_grades = {}
        for pr in placementrounds:
            path = pathname + f"{pr.id}.csv"
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                pid = str(row['participantId'])
                if pid not in id_to_student:
                    continue
                if pd.notna(row['grade']) and int(row['grade']) < 10:
                    participant_grades.setdefault(pid, set()).add(int(row['grade']))

        resolved = {}
        for pid, grades in participant_grades.items():
            if len(grades) <= 1:
                continue
            student = id_to_student[pid]
            current_sp = student.current_school_sp
            if current_sp is None or (isinstance(current_sp, float) and pd.isna(current_sp)):
                continue
            matching_grades = [g for g in grades if (current_sp, g) in spgrade_to_spgid]
            if len(matching_grades) == 1:
                resolved[pid] = matching_grades[0]
            elif pid in self._get_manual_grade_overrides():
                resolved[pid] = self._get_manual_grade_overrides()[pid]
            else:
                raise ValueError(f"Cannot resolve grade for student {pid}: grades {grades}, current_school_sp {current_sp}, matching grades {matching_grades}")
        if resolved:
            print(f"Resolved {len(resolved)} multi-grade students to single grade via current_school_sp.")
        return resolved

    def _get_manual_grade_overrides(self) -> dict:
        """Manual grade overrides for students where current_school_sp matches multiple grades.

        Read from exclusions/manual_grade_overrides.csv (columns: municipality,
        participantId, grade), which is header-only in this repository -- the
        synthetic dataset never produces an ambiguous participant. A gitignored
        .local.csv supplies real values. `replication_rr` reads the same file.
        With no override, an ambiguous participant raises.
        """
        from functions import exclusions_io
        return exclusions_io.manual_grade_overrides(self.municipality)

    def _add_legacy_spid_entries(self, spgrade_to_spgid, municipality) -> dict:
        """For each legacy spid that maps to a new spid (from Get_Schools._get_updated_spid),
        copy the (new_spid, grade) -> spgid entries under the legacy (old_spid, grade) key,
        so student-side lookups keyed on the old spid still resolve."""
        from functions.get_data_impl.get_data_schools import Get_Schools
        updated_spid_map = Get_Schools()._get_updated_spid(municipality)
        for old_spid, new_spid in updated_spid_map.items():
            for (spid, grade), spgid in list(spgrade_to_spgid.items()):
                if spid == new_spid:
                    spgrade_to_spgid[(old_spid, grade)] = spgid
        return spgrade_to_spgid
    
    def _get_random_application_date(self, application_date_raw, randomise_dates, placementround, participantid) -> str:
        """Return either the original application_date or a quasi-random date within the same year and half-year."""
        application_date = application_date_raw
        if application_date is None:
            placementround_obj = self.id_to_pr_dict.get(placementround)
            application_date = placementround_obj.application_end
        if randomise_dates:
            return self._get_quasirandom_date(application_date, participantid)
        else:
            return application_date
    
    def _format_date(self, value) -> str | None:
        """Normalize datetime-like strings to 'YYYY/MM/DD'. Return None if missing/invalid."""
        if value is None:
            return None
        try:
            ts = pd.to_datetime(value, errors='coerce', dayfirst=False)
            if pd.isna(ts):
                return None
            return ts.strftime('%Y/%m/%d')
        except Exception:
            return None
        
    def _is_valid_date(self, value) -> bool:
        """Return True if value can be parsed as a date, False otherwise."""
        if value is None:
            return False
        ts = pd.to_datetime(value, errors='coerce', dayfirst=False)
        return not pd.isna(ts)

    def _get_quasirandom_date(self, application_date, participantid) -> str:
        """Return a quasi-random date string within the same year and half-year as application_date.

        The offset is drawn from Random(f"{CURRENT_SEED}:date:{participantid}")
        rather than from the shared stream, for the same reason as the lottery
        number above: it then depends only on the seed and the participant id,
        not on how many numbers were drawn before it. That is what lets
        `original` and `replication_rr` be compared draw-for-draw rather than
        only in distribution.

        Raises ValueError if the input is missing or invalid.
        """
        if not self._is_valid_date(application_date):
            raise ValueError(f"Invalid application_date: {application_date!r}")

        ts = pd.to_datetime(application_date, dayfirst=False)
        year = ts.year
        # half-year bounds
        if ts.month <= 6:
            start = pd.Timestamp(year=year, month=1, day=1)
            end = pd.Timestamp(year=year, month=6, day=29)
        else:
            start = pd.Timestamp(year=year, month=7, day=1)
            end = pd.Timestamp(year=year, month=12, day=31)
        # Clip the half-year to overall possible_application_dates then sample uniformly.
        overall_earliest = pd.to_datetime(self.possible_application_dates.get('earliest'), errors='coerce', dayfirst=False)
        overall_latest = pd.to_datetime(self.possible_application_dates.get('latest'), errors='coerce', dayfirst=False)

        if not pd.isna(overall_earliest):
            start = start if start >= overall_earliest else overall_earliest
        if not pd.isna(overall_latest):
            end = end if end <= overall_latest else overall_latest

        if start > end:
            return pd.to_datetime(application_date, dayfirst=False).strftime('%Y/%m/%d')

        days = (end - start).days
        offset = 0 if days <= 0 else random.Random(
            f"{CURRENT_SEED}:date:{participantid}").randint(0, days)
        rand_date = start + pd.Timedelta(days=offset)
        return rand_date.strftime('%Y/%m/%d')