"""Select the 12 test names from the Crabtree et al. (2023) validated names data.

Inputs (both in data/names/):
  crabtree2023_full_data.json  per-name ratings, copied from the name selector's repo
  ssa_first_name_sex.csv       share of US births with each first name recorded as female

Output: materials/names.csv

Rules, applied in order:
  1. Groups: dataset identity "Black or African American" -> Black, "White" -> white.
  2. Gender: a first name counts as female when at least 90 percent of SSA births with
     it are female, male when at most 10 percent are. Anything in between is dropped.
  3. Drop the first names in the title of Bertrand and Mullainathan (2004), the most
     widely repeated audit study names: Emily, Greg, Lakisha, Jamal.
  4. Keep names that at least two thirds of respondents assigned to the intended race.
  5. Within a group, the three names have distinct surnames and use as many distinct
     first names as the eligible pool allows.
  6. Class match: every group's mean perceived income and mean perceived education must
     sit within 0.10 of every other group's, on the dataset's ordinal scales. Among the
     sets that satisfy that, pick the one whose weakest group has the highest mean
     correct identification rate, then the highest overall rate.
  7. The degree swap uses one name per group: the name in that group's set with the
     highest correct identification rate.
"""

import csv
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "names"
OUT = ROOT / "materials" / "names.csv"

RACE = {"Black or African American": "Black", "White": "white"}
GENDER_CUTOFF = 0.90
TITLE_NAMES = {"Emily", "Greg", "Lakisha", "Jamal"}
MIN_CORRECT = 2 / 3
CLASS_GAP = 0.10
GROUP_ORDER = [("Black", "F"), ("Black", "M"), ("white", "F"), ("white", "M")]


def load_pool() -> dict[tuple[str, str], list[dict]]:
    share = {}
    with (DATA / "ssa_first_name_sex.csv").open() as fh:
        for row in csv.DictReader(fh):
            share[row["first"]] = float(row["share_female"])
    pool: dict[tuple[str, str], list[dict]] = {g: [] for g in GROUP_ORDER}
    for row in json.loads((DATA / "crabtree2023_full_data.json").read_text()):
        race = RACE.get(row["identity"])
        if race is None or row["first"] in TITLE_NAMES:
            continue
        female_share = share[row["first"]]
        if female_share >= GENDER_CUTOFF:
            gender = "F"
        elif female_share <= 1 - GENDER_CUTOFF:
            gender = "M"
        else:
            continue
        if row["mean_correct"] < MIN_CORRECT:
            continue
        pool[(race, gender)].append(row | {"race": race, "gender": gender})
    return pool


def triples(names: list[dict]) -> list[tuple[dict, dict, dict]]:
    combos = [c for c in itertools.combinations(names, 3) if len({n["last"] for n in c}) == 3]
    most_firsts = max(len({n["first"] for n in c}) for c in combos)
    return [c for c in combos if len({n["first"] for n in c}) == most_firsts]


def select(pool: dict[tuple[str, str], list[dict]]) -> dict[tuple[str, str], tuple]:
    options = {g: triples(pool[g]) for g in GROUP_ORDER}
    stats = {
        g: np.array(
            [
                [
                    np.mean([n["avg_income"] for n in c]),
                    np.mean([n["avg_education"] for n in c]),
                    np.mean([n["mean_correct"] for n in c]),
                ]
                for c in opts
            ]
        )
        for g, opts in options.items()
    }
    # Any valid set fits in a box CLASS_GAP wide, so sweep box corners on a fine grid.
    lo = min(s[:, :2].min() for s in stats.values())
    hi = max(s[:, :2].max() for s in stats.values())
    grid = np.round(np.arange(lo - CLASS_GAP, hi + 0.005, 0.005), 4)
    best_key, best = None, None
    for inc0 in grid:
        for edu0 in grid:
            picks = {}
            for g, s in stats.items():
                ok = (
                    (s[:, 0] >= inc0 - 1e-9)
                    & (s[:, 0] <= inc0 + CLASS_GAP + 1e-9)
                    & (s[:, 1] >= edu0 - 1e-9)
                    & (s[:, 1] <= edu0 + CLASS_GAP + 1e-9)
                )
                if not ok.any():
                    break
                idx = np.flatnonzero(ok)
                picks[g] = int(idx[np.argmax(s[idx, 2])])
            else:
                rates = [stats[g][i, 2] for g, i in picks.items()]
                key = (round(min(rates), 6), round(float(np.mean(rates)), 6))
                if best_key is None or key > best_key:
                    best_key, best = key, picks
    if best is None:
        raise SystemExit("no name set satisfies the class match rule")
    return {g: options[g][i] for g, i in best.items()}


def main() -> None:
    pool = load_pool()
    chosen = select(pool)
    rows = []
    for g in GROUP_ORDER:
        names = sorted(chosen[g], key=lambda n: -n["mean_correct"])
        for rank, n in enumerate(names):
            rows.append(
                {
                    "name": n["name"],
                    "first": n["first"],
                    "last": n["last"],
                    "race": n["race"],
                    "gender": n["gender"],
                    "degree_swap": "yes" if rank == 0 else "no",
                    "mean_correct": f"{n['mean_correct']:.4f}",
                    "avg_income": f"{n['avg_income']:.4f}",
                    "avg_education": f"{n['avg_education']:.4f}",
                    "avg_citizenship": f"{n['avg_citizenship']:.4f}",
                }
            )
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for g in GROUP_ORDER:
        group = [r for r in rows if (r["race"], r["gender"]) == g]
        means = [
            np.mean([float(r[k]) for r in group])
            for k in ("mean_correct", "avg_income", "avg_education")
        ]
        print(
            f"{g[0]:5} {g[1]}  pool={len(pool[g]):3}  "
            f"correct={means[0]:.3f} income={means[1]:.3f} education={means[2]:.3f}  "
            + ", ".join(r["name"] for r in group)
        )


if __name__ == "__main__":
    main()
