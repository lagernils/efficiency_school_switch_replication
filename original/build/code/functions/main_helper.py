import pandas as pd
from typing import Tuple, List

class Helper:
    """Helper utilities used by `main.py`."""

    def get_years(self, municipality: str) -> list:
        per_municipality = {
            'Malmö': [2020, 2021, 2022, 2023, 2024, 2025],
            'Linköping': [2020, 2021, 2022, 2023, 2024, 2025],
            'Nacka': [2021, 2022, 2023, 2024, 2025],
            'Norrköping': [2022, 2023, 2024, 2025],
            'Uppsala': [2021, 2022, 2023, 2024, 2025, 2026],
            'Växjö': [2023, 2024, 2025],
        }
        if municipality not in per_municipality:
            raise ValueError(f"Unknown municipality: {municipality}")
        return per_municipality[municipality]

    def get_empty_stats_dict(self, years, k_intervals) -> dict:
        """Initialize an empty nested statistics dictionary structure."""
        stats = {}
        for year in years:
            stats[year] = {}
            for k in k_intervals:
                stats[year][k] = {}
        return stats
    
    def print_all_stats(self, stats, k_intervals, test_mode) -> None:
        """Prints aggregated statistics across all years and grades."""

        print("FINAL STATISTICS SUMMARY:")
        stats_by_k = {}
        stats_by_k_grade = {}
        for k in k_intervals:
            stats_by_k[k] = {'total_nr_students': 0, 'nr_switchers': 0,'percent_switchers': 0, 'nr_first_preference_switchers': 0, 'percent_first_preference_switchers': 0, 'nr_blocking_pairs': 0, 'nr_students_with_a_blocking_pair': 0, 'avg_waiting_time_total': 0.0, 'avg_waiting_time_switchers': 0.0, 'total_waiting_time': 0, 'total_waiting_time_switchers': 0, 'price_switch_by_BP': 0.0}
            stats_by_k_grade[k] = {}
            for grade in range(0,10):
                stats_by_k_grade[k][grade] = {'total_nr_students': 0, 'nr_switchers': 0, 'percent_switchers': 0,'nr_first_preference_switchers': 0, 'percent_first_preference_switchers': 0, 'nr_blocking_pairs': 0, 'nr_students_with_a_blocking_pair': 0, 'avg_waiting_time_total': 0.0, 'avg_waiting_time_switchers': 0.0, 'total_waiting_time': 0, 'total_waiting_time_switchers': 0, 'price_switch_by_BP': 0.0}
                for year in stats.keys():
                    if grade in stats[year][k]:
                        stats_by_k, stats_by_k_grade = self._update_stats(stats_by_k, stats_by_k_grade, k, grade, stats[year][k][grade])
        stats_by_k, stats_by_k_grade = self._compute_avgs(stats_by_k, stats_by_k_grade, k_intervals)
        for k in k_intervals:
            for stat_key in stats_by_k[k]:
                print(f"Overall stat for k={k} - {stat_key}: {stats_by_k[k][stat_key]}")
        return stats_by_k

    def _update_stats(self, stats_by_k, stats_by_k_grade, k, grade, stats_k_grade_year) -> Tuple[dict, dict]:
        """Update aggregated statistics with new data from a specific year and grade."""

        stats_by_k[k]['total_nr_students'] += stats_k_grade_year.get('total_nr_students', 0)
        stats_by_k_grade[k][grade]['total_nr_students'] += stats_k_grade_year.get('total_nr_students', 0)
        stats_by_k[k]['nr_switchers'] += stats_k_grade_year.get('nr_switchers', 0)
        stats_by_k_grade[k][grade]['nr_switchers'] += stats_k_grade_year.get('nr_switchers', 0)
        stats_by_k[k]['nr_first_preference_switchers'] = stats_by_k[k].get('nr_first_preference_switchers', 0) + stats_k_grade_year.get('nr_first_preference_switchers', 0)
        stats_by_k_grade[k][grade]['nr_first_preference_switchers'] = stats_by_k_grade[k][grade].get('nr_first_preference_switchers', 0) + stats_k_grade_year.get('nr_first_preference_switchers', 0)
        stats_by_k[k]['nr_blocking_pairs'] += stats_k_grade_year.get('nr_blocking_pairs', 0)
        stats_by_k_grade[k][grade]['nr_blocking_pairs'] += stats_k_grade_year.get('nr_blocking_pairs', 0)
        stats_by_k[k]['nr_students_with_a_blocking_pair'] = stats_by_k[k].get('nr_students_with_a_blocking_pair', 0) + stats_k_grade_year.get('nr_students_with_a_blocking_pair', 0)
        stats_by_k_grade[k][grade]['nr_students_with_a_blocking_pair'] = stats_by_k_grade[k][grade].get('nr_students_with_a_blocking_pair', 0) + stats_k_grade_year.get('nr_students_with_a_blocking_pair', 0)
        stats_by_k[k]['total_waiting_time'] += stats_k_grade_year.get('total_waiting_time', 0)
        stats_by_k_grade[k][grade]['total_waiting_time'] += stats_k_grade_year.get('total_waiting_time', 0)
        stats_by_k[k]['total_waiting_time_switchers'] += stats_k_grade_year.get('total_waiting_time_switchers', 0)
        stats_by_k_grade[k][grade]['total_waiting_time_switchers'] += stats_k_grade_year.get('total_waiting_time_switchers', 0)
        return stats_by_k, stats_by_k_grade
    
    def _compute_avgs(self, stats_by_k, stats_by_k_grade, k_intervals) -> Tuple[dict, dict]:
        """Compute average statistics after aggregating totals."""

        for k in k_intervals:
            stats_by_k[k]['percent_switchers'] = round((stats_by_k[k]['nr_switchers'] / stats_by_k[k]['total_nr_students']) * 100, 2) if stats_by_k[k]['total_nr_students'] > 0 else 0.0
            stats_by_k[k]['percent_first_preference_switchers'] = round((stats_by_k[k]['nr_first_preference_switchers'] / stats_by_k[k]['total_nr_students']) * 100, 2) if stats_by_k[k]['total_nr_students'] > 0 else 0.0
            stats_by_k[k]['avg_waiting_time_total'] = round(stats_by_k[k]['total_waiting_time'] / stats_by_k[k]['total_nr_students'], 2) if stats_by_k[k]['total_nr_students'] > 0 else 0.0
            stats_by_k[k]['avg_waiting_time_switchers'] = round(stats_by_k[k]['total_waiting_time_switchers'] / stats_by_k[k]['nr_switchers'], 2) if stats_by_k[k]['nr_switchers'] > 0 else 0.0
            stats_by_k[k]['price_switch_by_BP'] = round(stats_by_k[k]['nr_blocking_pairs'] / stats_by_k[k]['nr_switchers'], 2) if stats_by_k[k]['nr_switchers'] > 0 else 0.0
            for grade in range(0,10):
                stats_by_k_grade[k][grade]['percent_switchers'] = round((stats_by_k_grade[k][grade]['nr_switchers'] / stats_by_k_grade[k][grade]['total_nr_students']) * 100, 2) if stats_by_k_grade[k][grade]['total_nr_students'] > 0 else 0.0
                stats_by_k_grade[k][grade]['percent_first_preference_switchers'] = round((stats_by_k_grade[k][grade]['nr_first_preference_switchers'] / stats_by_k_grade[k][grade]['total_nr_students']) * 100, 2) if stats_by_k_grade[k][grade]['total_nr_students'] > 0 else 0.0
                stats_by_k_grade[k][grade]['avg_waiting_time_total'] = round(stats_by_k_grade[k][grade]['total_waiting_time'] / stats_by_k_grade[k][grade]['total_nr_students'], 2) if stats_by_k_grade[k][grade]['total_nr_students'] > 0 else 0.0
                stats_by_k_grade[k][grade]['avg_waiting_time_switchers'] = round(stats_by_k_grade[k][grade]['total_waiting_time_switchers'] / stats_by_k_grade[k][grade]['nr_switchers'], 2) if stats_by_k_grade[k][grade]['nr_switchers'] > 0 else 0.0
                stats_by_k_grade[k][grade]['price_switch_by_BP'] = round(stats_by_k_grade[k][grade]['nr_blocking_pairs'] / stats_by_k_grade[k][grade]['nr_switchers'], 2) if stats_by_k_grade[k][grade]['nr_switchers'] > 0 else 0.0
        return stats_by_k, stats_by_k_grade
    
    def print_placements(self, students_with_placement_this_round, students_with_placement, students_without_placement) -> None:
        """Prints the placements of students for debugging purposes."""

        print("Students with placement this round:")
        for student in students_with_placement_this_round:
            for school in student.placement.keys():
                if student.placement[school]:
                    print(f"Student {student.participantid} placed at {school} in this round.")
        print("All students with placement so far:")
        for student in students_with_placement:
            for school in student.placement.keys():
                if student.placement[school]:
                    print(f"Student {student.participantid} placed at {school}")
        print("Students without placement:")
        for student in students_without_placement:
            print(f"Student {student.participantid} has no placement.")

    def check_capacity_constraints(self, all_students, all_schools,
                                   extra_seats_by_school=None,
                                   base_capacity: int = 0) -> None:
        """Checks that no school exceeds its capacity after placements. Raises ValueError if a violation is found.
        School capacity is defined as the number of students initially assigned to the school that were displaced,
        PLUS that school's allowance of additional empty seats.
        Number of new students with placement at the school should not exceed that total.

        `extra_seats_by_school` maps (year, grade, spgid) -> extra seats, as
        produced per market by update_round.allocate_extra_seats. Pass None to
        use the flat `base_capacity` allowance instead. With no slack at all
        (the paper's baseline) the allowance is 0 and this reduces to the
        original equality test, displaced == placed.
        ."""
        partid_to_student = {student.participantid: student for student in all_students}
        for school in all_schools:
            displaced_students = 0
            for participantid in school.current_students:
                student = partid_to_student[participantid]
                if not student.documentation_placement[school.spgid]:
                    displaced_students += 1
            # Baseline (no slack): a school may take in exactly as many students
            # as it loses, so displaced == placed. With additional empty seats
            # the school may take in MORE than it loses, but never more than its
            # own extra-seat allowance -- so the invariant generalises to
            #     placed - displaced <= allowance
            # and collapses back to the equality above when allowance == 0.
            allowance = (base_capacity if extra_seats_by_school is None
                         else extra_seats_by_school.get(
                             (school.year, school.grade, school.spgid), 0))
            if len(school.placed_studentobjs) - displaced_students <= allowance:
                #print(f"Capacity constraints OK at school {school.spgid} ({school.name}): initial nr of students {len(school.current_students)}, displaced {displaced_students}, placed {len(school.placed_studentobjs)}")
                continue
            else:
                print('Initial students at school:')
                for participantid in school.current_students:
                    print(f"  Participant ID: {participantid}")
                print('Displaced students:')
                for participantid in school.current_students:
                    student = partid_to_student[participantid]
                    if not student.documentation_placement[school.spgid]:
                        print(f"  Participant ID: {participantid}")
                print('Current students not displaced:')
                for participantid in school.current_students:
                    student = partid_to_student[participantid]
                    if student.documentation_placement[school.spgid]:
                        print(f"  Participant ID: {participantid}")
                        #for attribute in vars(student):
                        #    print(f"  {attribute}: {getattr(student, attribute)}")
                        #print(f"  Participant ID: {participantid} has documentation_placement dict: {student.documentation_placement}")
                        #print(f"  Participant ID: {participantid} has placement dict: {student.placement}")
                        #print(f"  Participant ID: {participantid} has current school spg: {student.current_school_spg}")
                        #print(f"  Participant ID: {participantid} has current placement_pr: {getattr(student, 'placement_pr', None)}")
                print('Placed students:')
                for student in school.placed_studentobjs:
                    print(f"  Participant ID: {student.participantid}")
                    #for attribute in vars(student):
                    #    print(f"    {attribute}: {getattr(student, attribute)}")
                print(f"Capacity constraint violation at school {school.spgid} ({school.name}): initial nr of students {len(school.current_students)}, displaced {displaced_students}, placed {len(school.placed_studentobjs)}")
                raise ValueError("Capacity constraint violation detected.")

    def summarise_across_municipalities(self, municipalities: list, algos=('DA', 'TTC')) -> None:
        """Combine per-municipality loop_results CSVs into a single summary using law of total variance.
        Produces one CSV per algo: summary_stats_{algo}_ALL.csv"""
        import numpy as np
        from pathlib import Path

        outdir = Path(__file__).resolve().parents[3] / 'build' / 'output' / 'loop_results'
        count_stats = ['total_nr_students', 'nr_switchers', 'nr_first_preference_switchers',
                       'nr_blocking_pairs', 'nr_students_with_a_blocking_pair',
                       'total_waiting_time', 'total_waiting_time_switchers']

        for algo in algos:
            dfs = {}
            for muni in municipalities:
                path = outdir / f'summary_stats_{algo}_{muni}.csv'
                dfs[muni] = pd.read_csv(path, index_col='k')

            k_values = dfs[municipalities[0]].index
            rows = []
            for k in k_values:
                row = {'k': k}
                n = {m: dfs[m].loc[k, 'total_nr_students_mean'] for m in municipalities}
                N = sum(n.values())

                for stat in count_stats:
                    means = {m: dfs[m].loc[k, f'{stat}_mean'] for m in municipalities}
                    stds = {m: dfs[m].loc[k, f'{stat}_std'] for m in municipalities}
                    total_mean = sum(means.values())
                    within_var = sum(n[m] * stds[m]**2 for m in municipalities) / N
                    between_var = sum(n[m] * (means[m] - total_mean * n[m] / N)**2 for m in municipalities) / N
                    total_std = np.sqrt(within_var + between_var)
                    row[f'{stat}_mean'] = round(total_mean, 4)
                    row[f'{stat}_std'] = round(total_std, 4)

                row['percent_switchers_mean'] = round(row['nr_switchers_mean'] / row['total_nr_students_mean'] * 100, 4)
                row['percent_first_preference_switchers_mean'] = round(row['nr_first_preference_switchers_mean'] / row['total_nr_students_mean'] * 100, 4)
                row['avg_waiting_time_total_mean'] = round(row['total_waiting_time_mean'] / row['total_nr_students_mean'], 4)
                row['avg_waiting_time_switchers_mean'] = round(row['total_waiting_time_switchers_mean'] / row['nr_switchers_mean'], 4) if row['nr_switchers_mean'] > 0 else 0.0
                row['price_switch_by_BP_mean'] = round(row['nr_blocking_pairs_mean'] / row['nr_switchers_mean'], 4) if row['nr_switchers_mean'] > 0 else 0.0

                for derived in ['percent_switchers', 'percent_first_preference_switchers',
                                'avg_waiting_time_total', 'avg_waiting_time_switchers', 'price_switch_by_BP']:
                    row[f'{derived}_std'] = 0.0

                rows.append(row)

            col_order = dfs[municipalities[0]].columns.tolist()
            col_order = ['k'] + col_order
            out_df = pd.DataFrame(rows)[col_order]
            outpath = outdir / f'summary_stats_{algo}_ALL.csv'
            out_df.to_csv(outpath, index=False)
            print(f"Wrote combined summary to {outpath}")