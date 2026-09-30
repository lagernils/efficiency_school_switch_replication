import pandas as pd
from functions.get_data import PlacementRound
from functions import exclusions_io
from typing import List, Tuple, Dict

class Get_PlacementRounds():

    def get(self, pathnames, municipality) -> List[PlacementRound]:
        """Retrieve and construct list of PlacementRound objects from CSV pathnames."""
        self.municipality = municipality
        placement_rounds = self.get_csv_pr(pathnames["placementrounds"])
        self.id_to_pr_dict = {pr.id: pr for pr in placement_rounds} # Mapping id->PlacementRound
        placement_rounds = self.get_csv_prperiod(pathnames["placementroundperiods"], placement_rounds) # Update PlacementRound objects with period info
        return placement_rounds

    def get_csv_pr(self, pathname) -> List[PlacementRound]:
        """Read placement rounds CSV and return list of PlacementRound dataclass instances."""
        # Read the CSV file
        rounds_to_ignore = self._get_rounds_to_ignore(self.municipality)
        df = pd.read_csv(pathname)
        
        # Filter out rows where placementRoundId is in rounds_to_ignore
        df = df[~df['placementRoundId'].isin(rounds_to_ignore)]
        
        # Create PlacementRound objects
        placement_rounds = []
        for _, row in df.iterrows():
            pr = PlacementRound(
                id=int(row['placementRoundId']),
                municipality=row['municipalityId'],
                name=row['roundName'],
                year=row['academicYear'],
                grade=None,  # Not available in this CSV
                application_start=None,  # Not available in this CSV
                application_end=None,  # Not available in this CSV
                results_release=None,  # Not available in this CSV
                acceptance_deadline=None,  # Not available in this CSV
                school_start_date=self._format_date(row.get('schoolStartDate')),
                applicable_spgs=[],
                list_of_raw_placementrounds=[],
            )
            placement_rounds.append(pr)
        
        return placement_rounds

    def get_csv_prperiod(self, pathname, placement_rounds) -> List[PlacementRound]:
        """Read placement round periods CSV and update PlacementRound objects.

        CSV columns expected: 'placementRoundId', 'stage', 'startPeriod', 'endPeriod'

        Rules:
        - If stage == 'OPEN_FOR_REQUESTS': set application_start and application_end
        - If stage == 'OPEN_FOR_PLACEMENT_NOTIFICATION': set results_release and acceptance_deadline
        """
        # Ensure id->placementround mapping exists
        if not hasattr(self, 'id_to_pr_dict') or self.id_to_pr_dict is None:
            self.id_to_pr_dict = {pr.id: pr for pr in placement_rounds}

        # Read periods CSV
        df = pd.read_csv(pathname)

        for _, row in df.iterrows():
            try:
                pid = int(row['placementRoundId'])
            except Exception:
                # Skip rows with invalid/missing id
                continue

            pr = self.id_to_pr_dict.get(pid)
            if pr is None:
                # No matching placement round (maybe filtered out); skip
                continue

            stage = row.get('stage')
            start = self._format_date(row.get('startPeriod'))
            end = self._format_date(row.get('endPeriod'))

            if stage == 'OPEN_FOR_REQUESTS':
                pr.application_start = start
                pr.application_end = end
            elif stage == 'OPEN_FOR_PLACEMENT_NOTIFICATION':
                pr.results_release = start
                pr.acceptance_deadline = end

        return placement_rounds
    
    def _get_rounds_to_ignore(self, municipality) -> List[int]:
        """Placement round IDs to ignore for this municipality.

        Test rounds, rounds opened and never used, and rounds belonging to a
        different placement process. The identifiers come from the source
        system, so the list lives in exclusions/excluded_rounds.csv rather than
        here; that file is header-only in this repository, which means no round
        is excluded on the synthetic dataset. `replication_rr` reads the same
        file. See exclusions/README.md.
        """
        return exclusions_io.excluded_round_ids(municipality)
    
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
