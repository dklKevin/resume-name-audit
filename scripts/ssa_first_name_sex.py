"""Build data/names/ssa_first_name_sex.csv from US Social Security baby name counts.

The counts come from the `babynames` R package (hadley/babynames, data/babynames.rda),
which packages the SSA national baby name files for 1880 to 2017. Only first names that
appear in the validated names data for the Black and white groups are kept.

Run with: uv run --with rdata --with pandas python scripts/ssa_first_name_sex.py <babynames.rda>
"""

import csv
import json
import sys
from pathlib import Path

import rdata

ROOT = Path(__file__).resolve().parent.parent
NAMES = ROOT / "data" / "names" / "crabtree2023_full_data.json"
OUT = ROOT / "data" / "names" / "ssa_first_name_sex.csv"
GROUPS = {"Black or African American", "White"}


def main(rda_path: str) -> None:
    rows = json.loads(NAMES.read_text())
    firsts = sorted({r["first"] for r in rows if r["identity"] in GROUPS})
    frame = rdata.conversion.convert(rdata.parser.parse_file(rda_path))["babynames"]
    frame = frame[frame["name"].isin(firsts)]
    counts = frame.groupby(["name", "sex"])["n"].sum().unstack(fill_value=0)
    with OUT.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["first", "births_female", "births_male", "share_female"])
        for first in firsts:
            female = int(counts.loc[first].get("F", 0)) if first in counts.index else 0
            male = int(counts.loc[first].get("M", 0)) if first in counts.index else 0
            share = female / (female + male) if female + male else ""
            writer.writerow([first, female, male, f"{share:.4f}" if share != "" else ""])


if __name__ == "__main__":
    main(sys.argv[1])
