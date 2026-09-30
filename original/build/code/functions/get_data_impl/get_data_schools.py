import pandas as pd
from functions.get_data import School
from functions import exclusions_io
from typing import List, Tuple, Dict

class Get_Schools():
    def get(self, pathnames, years, municipality) -> List[School]:
        self.municipality = municipality
        schools = self.get_csv_choosables(pathnames["choosables"], years)
        return schools

    def get_csv_choosables(self, pathname, years) -> List[School]:
        """Read choosables CSV and return list of School dataclass objects.

        Expected columns (used):
        - choosableId -> school.choosableid
        - schoolProgramId -> school.spid
        - schoolProgramGradeId -> school.spgid
        - placementRoundId -> school.placementround
        - grade -> school.grade
        - cgy_overrideCapacity -> school.capacity

        Fields `cutoff` and `available_seats` are set to None as requested.
        """
        df = pd.read_csv(pathname)

        schools = []
        year_to_spgid_set = {year: set() for year in years}
        year_to_spgid_to_school = {year: {} for year in years}
        for _, row in df.iterrows():
            #self._get_row(row, years, year_to_spgid_set, year_to_spgid_to_school, schools)
            spid, spgid = self._get_schoolids(row)
            if int(row['grade']) >= 10:
                continue
            capacity = int(row['cgy_overrideCapacity']) if pd.notna(row['cgy_overrideCapacity']) else None

            for year in years: # Schools can appear in multiple academic years
                spgid_to_school = year_to_spgid_to_school[year]
                if spgid in spgid_to_school:
                    school = spgid_to_school.get(spgid)
                    school.choosableid_list.append(str(row['choosableId']))
                    school.placementround_list.append(int(row['placementRoundId']))
                    school.capacity_dict[int(row['placementRoundId'])] = capacity
                    continue
                else:
                    school = School(
                        spgid=spgid,
                        spid=spid,
                        name= str(row['sp_programName']),  # Name not provided in choosables CSV
                        choosableid_list=[str(row['choosableId'])],
                        placementround_list=[int(row['placementRoundId'])],
                        year=year,
                        grade=int(row['grade']),
                        cutoff=None,
                        capacity_dict={int(row['placementRoundId']): capacity},
                        capacity=0, # to be set later based on placement round, don't use actual capacities
                        available_seats=None,
                        current_students=[],
                        placed_studentobjs=[]
                    )
                    year_to_spgid_set[year].add(spgid)
                    year_to_spgid_to_school[year][spgid] = school
                    schools.append(school)
        return schools

    def _get_row(self, row, years, year_to_spgid_set, year_to_spgid_to_school, schools) -> None:
        """Updates list of School objects based on a row from the choosables CSV."""
        spid, spgid = self._get_schoolids(row)
        capacity = int(row['cgy_overrideCapacity']) if pd.notna(row['cgy_overrideCapacity']) else None

        for year in years: # Schools can appear in multiple academic years
            spgid_to_school = year_to_spgid_to_school[year]
            if spgid in spgid_to_school:
                school = spgid_to_school.get(spgid)
                school.choosableid_list.append(str(row['choosableId']))
                school.placementround_list.append(int(row['placementRoundId']))
                school.capacity_dict[int(row['placementRoundId'])] = capacity
                continue
            else:
                school = School(
                    spgid=spgid,
                    spid=spid,
                    name= str(row['sp_programName']),  # Name not provided in choosables CSV
                    choosableid_list=[str(row['choosableId'])],
                    placementround_list=[int(row['placementRoundId'])],
                    year=year,
                    grade=int(row['grade']),
                    cutoff=None,
                    capacity_dict={int(row['placementRoundId']): capacity},
                    capacity=0, # to be set later based on placement round, don't use actual capacities
                    available_seats=None,
                    current_students=[],
                    placed_studentobjs=[]
                )
                year_to_spgid_set[year].add(spgid)
                year_to_spgid_to_school[year][spgid] = school
                schools.append(school)

    def _get_schoolids(self, row) -> Tuple[str | None, str | None]:
        """Some schoolProgramGradeIds and schoolProgramIds have been deprecated and replaced.
        This function maps deprecated IDs to updated IDs."""
        updated_spgid_map = self._get_updated_spgid(self.municipality)
        updated_spid_map = self._get_updated_spid(self.municipality)
        spid = str(row['schoolProgramId']) if 'schoolProgramId' in row and pd.notna(row['schoolProgramId']) else None
        spgid = str(row['schoolProgramGradeId']) if 'schoolProgramGradeId' in row and pd.notna(row['schoolProgramGradeId']) else None
        if spgid in updated_spgid_map.keys():
            spgid = updated_spgid_map[spgid]
            if spid in updated_spid_map.keys():
                spid = updated_spid_map[spid]
        return spid, spgid
    
    def _get_updated_spgid(self, municipality) -> Dict[str, str]:
        """Deprecated spgid -> updated spgid for this municipality.

        Some school programmes had their ids reissued mid-sample. The ids come
        from the source system, so the mapping lives in
        exclusions/spgid_remap.csv rather than here; that file is header-only in
        this repository. `replication_rr` reads the same file. See
        exclusions/README.md.
        """
        return exclusions_io.spgid_remap(municipality)

    def _get_updated_spid(self, municipality) -> Dict[str, str]:
        """Deprecated spid -> updated spid for this municipality.

        Same reasoning as _get_updated_spgid; values live in
        exclusions/spid_alias.csv.
        """
        return exclusions_io.spid_alias(municipality)
