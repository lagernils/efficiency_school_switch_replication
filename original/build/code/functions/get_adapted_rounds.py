from datetime import timedelta
import pandas as pd
from functions.get_data import PlacementRound


class Get_Adapted_Rounds:
    """Generate adapted placement rounds grid split by k-day intervals.

    This module creates a schedule of placement-round windows for each
    academic `year` and `grade`, where each window spans `k` days.
    The function returns a mapping `year -> grade -> [PlacementRound...]`
    and the final application end date as a formatted string.
    """

    def get(self, placementrounds, k, years) -> tuple[dict, str]:
        """Generate adapted placement rounds for each year and grade based on k-day intervals.
        Returns a dict mapping year -> grade -> list of PlacementRound objects,
        and the final application end date as a string in 'YYYY/MM/DD' format."""
        template_placementround_obj = placementrounds[0]
        year_grade_to_adapted = {}
        final_placement_dates = {}
        next_round_id = 1
        # Loop over each academic year
        for year in years:
            grade_to_rounds = {}
            window_start = pd.to_datetime(f"{year}-06-30") # Academic year start
            window_end = pd.to_datetime(f"{year+1}-06-29") # Academic year end
            # Determine interval start timestamps spaced by `k` days
            interval_starts = list(pd.date_range(start=window_start, end=window_end, freq=pd.Timedelta(days=k)))
            for _, interval_start_ts in enumerate(interval_starts, start=1): # For each interval start
                interval_end_ts = self._compute_interval_end(interval_start_ts, window_end, k) # Compute interval end, respecting academic year end
                final_placement_dates[year] = interval_end_ts.strftime('%Y/%m/%d') # keep updating to latest end date for this year
                #print(f"Year {year}, Interval starting {interval_start_ts.strftime('%Y/%m/%d')} to {interval_end_ts.strftime('%Y/%m/%d')}")
                for grade in range(0, 10): # Create a PlacementRound for each grade in this interval
                    if grade not in grade_to_rounds:
                        grade_to_rounds[grade] = []
                    # Create adapted PlacementRound object
                    grade_to_rounds[grade].append(self._make_round(next_round_id, interval_start_ts, interval_end_ts, template_placementround_obj, grade))
                    next_round_id += 1
            year_grade_to_adapted[year] = grade_to_rounds

        return year_grade_to_adapted, final_placement_dates
    
    def _compute_interval_end(self, interval_start_ts, window_end_ts, k) -> pd.Timestamp:
        """Compute this interval's end as the smaller of (interval_start + k - 1 days) and the overall window_end.
        Academic year ends on June 29, which must be respected.
        Ex: If interval_start is 2021/12/27, k=180, return +180 days later on 2022/06/24.
        If interval_start is 2022/06/24, k=180, then return 2022/06/29."""
        remaining_days = (window_end_ts - interval_start_ts).days
        if remaining_days < (k - 1):
            return window_end_ts #- timedelta(days=1)
        else:
            return interval_start_ts + timedelta(days=(k - 1))

    def _make_round(self, idx, start_ts, end_ts, template, grade) -> PlacementRound:
        return PlacementRound(
            id=idx,
            municipality=template.municipality,
            name='',
            year=template.year,
            grade=grade,
            application_start=start_ts.strftime('%Y/%m/%d'),
            application_end=end_ts.strftime('%Y/%m/%d'),
            results_release='',
            acceptance_deadline='',
            school_start_date='',
            applicable_spgs=[],
            list_of_raw_placementrounds=[],
        )

    
