"""Pilot checks run before the lock.

The pilot scores every resume once per model with one fixed name, at both degree levels.

  degree floor   the hard rule: for each model, the mean paired score gap between the
                 high and low degree versions must be at least 10 points
  advance rate   30 to 70 percent ADVANCE at the high degree, per model and pooled
  uniform        resumes that every model accepts, or every model rejects, at both degree
                 levels; at most 5 may remain

The degree floor is the one hard rule. The other two are targets, reported alongside it.
"""

from dataclasses import dataclass
from pathlib import Path

from .config import DEGREE_FLOOR, PILOT_ADVANCE_RANGE, PILOT_MAX_UNIFORM
from .harness import read_results


@dataclass
class ModelPilot:
    provider: str
    models_seen: list[str]
    resumes: int
    failed_calls: int
    advance_rate_high: float
    advance_rate_low: float
    mean_score_high: float
    mean_score_low: float
    degree_gap: float
    passes_degree_floor: bool
    in_advance_range: bool


@dataclass
class PilotReport:
    models: list[ModelPilot]
    always_advance: list[int]
    always_reject: list[int]
    overall_advance_high: float = float("nan")

    @property
    def passes(self) -> bool:
        """The hard rule: the degree floor holds for every model."""
        return all(m.passes_degree_floor for m in self.models)

    @property
    def meets_targets(self) -> bool:
        """The advance rate range and the uniform resume limit."""
        return (
            all(m.in_advance_range for m in self.models)
            and PILOT_ADVANCE_RANGE[0] <= self.overall_advance_high <= PILOT_ADVANCE_RANGE[1]
            and len(self.always_advance) + len(self.always_reject) <= PILOT_MAX_UNIFORM
        )


def merged_rows(run_dirs: list[Path]) -> list[dict]:
    """Later pilot runs replace earlier rows for the same provider and resume."""
    merged: dict[tuple[str, str], list[dict]] = {}
    for run_dir in run_dirs:
        fresh: dict[tuple[str, str], list[dict]] = {}
        for row in read_results(run_dir / "results.csv"):
            if row["condition"] == "pilot":
                fresh.setdefault((row["provider"], row["resume_id"]), []).append(row)
        merged.update(fresh)
    return [row for rows in merged.values() for row in rows]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def report(run_dirs: list[Path]) -> PilotReport:
    rows = merged_rows(run_dirs)
    ok = [r for r in rows if r["parse_ok"] == "true"]
    models = []
    for provider in sorted({r["provider"] for r in rows}):
        mine = [r for r in ok if r["provider"] == provider]
        high = {r["resume_id"]: r for r in mine if r["degree_level"] == "high"}
        low = {r["resume_id"]: r for r in mine if r["degree_level"] == "low"}
        paired = sorted(set(high) & set(low))
        gap = _mean([int(high[k]["score"]) - int(low[k]["score"]) for k in paired])
        rate_high = _mean([high[k]["decision"] == "ADVANCE" for k in high])
        models.append(
            ModelPilot(
                provider=provider,
                models_seen=sorted(
                    {r["model"] for r in rows if r["provider"] == provider and r["model"]}
                ),
                resumes=len({r["resume_id"] for r in rows if r["provider"] == provider}),
                failed_calls=sum(
                    r["parse_ok"] != "true" for r in rows if r["provider"] == provider
                ),
                advance_rate_high=rate_high,
                advance_rate_low=_mean([low[k]["decision"] == "ADVANCE" for k in low]),
                mean_score_high=_mean([int(high[k]["score"]) for k in high]),
                mean_score_low=_mean([int(low[k]["score"]) for k in low]),
                degree_gap=gap,
                passes_degree_floor=gap >= DEGREE_FLOOR,
                in_advance_range=PILOT_ADVANCE_RANGE[0] <= rate_high <= PILOT_ADVANCE_RANGE[1],
            )
        )
    decisions: dict[int, set[str]] = {}
    for r in ok:
        decisions.setdefault(int(r["resume_id"]), set()).add(r["decision"])
    always_advance = sorted(rid for rid, d in decisions.items() if d == {"ADVANCE"})
    always_reject = sorted(rid for rid, d in decisions.items() if d == {"REJECT"})
    high = [r for r in ok if r["degree_level"] == "high"]
    overall = _mean([r["decision"] == "ADVANCE" for r in high])
    return PilotReport(models, always_advance, always_reject, overall)


def render(rep: PilotReport) -> str:
    lines = ["# Pilot report", ""]
    lines.append(
        "| model | resumes | failed | ADVANCE high | ADVANCE low | mean high | mean low "
        "| degree gap | floor (10) | 30 to 70% |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for m in rep.models:
        lines.append(
            f"| {', '.join(m.models_seen) or m.provider} | {m.resumes} | {m.failed_calls} "
            f"| {m.advance_rate_high:.0%} | {m.advance_rate_low:.0%} "
            f"| {m.mean_score_high:.1f} | {m.mean_score_low:.1f} | {m.degree_gap:.1f} "
            f"| {'pass' if m.passes_degree_floor else 'FAIL'} "
            f"| {'yes' if m.in_advance_range else 'no'} |"
        )
    lines.append("")
    lines.append(
        f"Overall ADVANCE at the bachelor's level, both models pooled: "
        f"{rep.overall_advance_high:.0%}"
    )
    uniform = len(rep.always_advance) + len(rep.always_reject)
    lines.append(f"Resumes that never change outcome: {uniform} (at most {PILOT_MAX_UNIFORM})")
    lines.append(f"Always ADVANCE (every model, both degrees): {rep.always_advance or 'none'}")
    lines.append(f"Always REJECT (every model, both degrees): {rep.always_reject or 'none'}")
    lines.append("")
    lines.append(f"Degree floor (the hard rule): {'PASS' if rep.passes else 'FAIL'}")
    lines.append(
        f"Targets (advance range, uniform limit): {'met' if rep.meets_targets else 'not met'}"
    )
    return "\n".join(lines) + "\n"
