"""
Cross-municipality aggregation, combining per-municipality means and standard
deviations via the law of total variance.

Reads the per-municipality CSVs produced by Run_School_Switch and writes
`summary_stats_{DA|TTC}_ALL.csv`.
"""

import pandas as pd
from . import config
from .aggregation import aggregate_across_municipalities


class Helper:
    def summarise_across_municipalities(self, municipalities: list):
        out_dir = config.OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        for algo in ("DA", "TTC"):
            per_mun = {}
            for mun in municipalities:
                path = out_dir / f"summary_stats_{algo}_{mun}.csv"
                if path.exists():
                    per_mun[mun] = pd.read_csv(path)
            if not per_mun:
                print(f"[Helper] no per-municipality CSVs for {algo}; skipping")
                continue
            agg = aggregate_across_municipalities(per_mun)
            out = out_dir / f"summary_stats_{algo}_ALL.csv"
            agg.to_csv(out, index=False)
            print(f"[Helper] wrote {out.name}")
