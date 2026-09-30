
from dataclasses import dataclass, field

@dataclass
class PlacementRound:
    id: int
    municipality: str
    name: str
    year: int
    grade: int
    application_start: str
    application_end: str
    results_release: str
    acceptance_deadline: str
    school_start_date: str
    applicable_spgs: list
    list_of_raw_placementrounds: list

@dataclass
class Student:
    idx : int
    participantid: str
    studentid: str
    placementround_raw: int
    placementround: int 
    grade: int
    type: str
    application_date: str
    application_date_randomised: str
    year: int
    lottery_number: int
    applicable_spgs: list
    preferences_dict: dict
    preferences: list
    complete_preferences: list
    prioritygroup_dict: dict
    distances_dict: dict
    relativedistances_dict: dict
    prio_score: dict
    current_school_sp: str
    current_school_spg: str
    application_history: list
    preliminary_placed: bool
    last_pr_as_participant: int
    placement: dict
    placement_pr: int
    placement_date: str
    documentation_placement: dict
    documentation_application_history: list
    # EADAM-specific: consent (1=waives priority, 0=doesn't) and the working
    # preference list EADAM prunes during its internal DA re-runs. Kept
    # separate from `preferences`/`complete_preferences` so the originals
    # survive for downstream welfare analysis.
    consent: int = 1
    eadam_preferences: list = field(default_factory=list)

@dataclass
class School:
    spgid: str
    spid: str
    name: str
    choosableid_list: list
    placementround_list: list
    year: int
    grade: int
    cutoff: int
    capacity_dict: dict[str, int] # map pr to capacity
    capacity: int
    available_seats: int
    current_students: list
    placed_studentobjs: list[Student]

class Get_Data:
    def get(self, test_mode, which_test_mode, unit_demand_mode, years, randomise_dates, municipality, full_consent_bool: bool = True) -> dict:
        """Main function to get all data:
        placementrounds: list of PlacementRound objects,
        schools: list of School objects,
        students: list of Student objects.

        `full_consent_bool` is forwarded to Get_Students so each student's
        `consent` attribute is set at creation time (used by EADAM)."""
        if not test_mode:
            pathnames = self.get_pathnames(municipality)
        else:
            pathnames = self.get_pathnames_test(which_test_mode)

        # Get placement rounds
        from functions.get_data_impl.get_data_rounds import Get_PlacementRounds
        placementrounds = Get_PlacementRounds().get(pathnames, municipality)
        print(f"Loaded {len(placementrounds)} placement rounds.")
        for pr in placementrounds:
            print(f"Placement Round ID: {pr.id}, Year: {pr.year}, Name: {pr.name}")

        # Get schools
        from functions.get_data_impl.get_data_schools import Get_Schools
        schools = Get_Schools().get(pathnames, years, municipality)
        print(f"Loaded {len(schools)} schools.")

        # Get students
        from functions.get_data_impl.get_data_students import Get_Students
        students = Get_Students().get(pathnames, placementrounds, schools, unit_demand_mode, randomise_dates, municipality, full_consent_bool)
        print(f"Loaded {len(students)} students.")
  
        # Count number of first-choice, second-choice, etc. preferences across all students
        self.print_preference_counts(students)
        
        return {
            "placementrounds": placementrounds,
            "schools": schools,
            "students": students
        }
    
    def get_pathnames(self, municipality) -> dict:
        from functions import exclusions_io

        # Input data is shared by both implementations. It lives at raw/ in the
        # repository root by default, or wherever SCHOOL_SWITCH_RAW_DIR points,
        # so that `original` and `replication_rr` read byte-identical inputs.
        raw_dir = exclusions_io.raw_root() / municipality
        if not raw_dir.exists():
            raise FileNotFoundError(
                "raw data not found at {p}.\nThe real data is not distributed with this package (see raw/README.md).\nRun  python3 tools/make_synthetic_data.py  to create a synthetic dataset,\nor set SCHOOL_SWITCH_RAW_DIR to a directory that holds your own extracts.".format(p=raw_dir))

        return {
            "placementrounds": str(raw_dir / "2.1.1 Rundor.csv"),
            "placementroundperiods": str(raw_dir / "2.1.2 PlacementRoundPeriod.csv"),
            "participants": str(raw_dir / "2.2 Participant.csv"),
            "choosables": str(raw_dir / "2.3 Chooseables.csv"),
            "mappings": str(raw_dir / "2.4 Participant-PriorityGround - Round "),
        }
    
    def get_pathnames_test(self, which_test_mode) -> dict:
        from functions import exclusions_io

        # Hand-built worked examples shipped with the repository; they do not
        # depend on raw/ or SCHOOL_SWITCH_RAW_DIR.
        fixtures = exclusions_io.REPO_ROOT / 'tests' / 'fixtures'
        if which_test_mode == 'basic':
            raw_dir = fixtures / 'Test'
        elif which_test_mode == 'nonmonotone':
            raw_dir = fixtures / 'Test_NonMonotone'
        elif which_test_mode == 'blockingpair':
            raw_dir = fixtures / 'Test_BlockingPair'

        return {
            "placementrounds": str(raw_dir / "TEST 2.1.1 Rundor.csv"),
            "placementroundperiods": str(raw_dir / "TEST 2.1.2 PlacementRoundPeriod.csv"),
            "participants": str(raw_dir / "TEST 2.2 Participant.csv"),
            "choosables": str(raw_dir / "TEST 2.3 Chooseables.csv"),
            "mappings": str(raw_dir / "TEST 2.4 Participant-PriorityGround - Round "),
        }
    
    def print_preference_counts(self, students) -> None:
        choice_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for student in students:
            for key in choice_counts.keys():
                if key in student.preferences_dict.values():
                    choice_counts[key] += 1
                else:
                    if key == 1:
                        print(f"Student {student.participantid} in placement round {student.placementround} has no first choice preference!")
                        print(f"  Preferences dict: {student.preferences_dict}")
        print("Preference counts across all students:")
        for choice, count in choice_counts.items():
            print(f"  Choice {choice}: {count} students")