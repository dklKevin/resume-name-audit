import math

import numpy as np
import pytest

from name_audit import metrics

DEGREE_NAMES = {"Ann", "Cal", "Eve", "Gus"}
GROUP_NAMES = {
    ("Black", "F"): ["Ann", "Bea"],
    ("Black", "M"): ["Cal", "Dan"],
    ("white", "F"): ["Eve", "Fay"],
    ("white", "M"): ["Gus", "Hal"],
}


def row(resume, name, race, gender, score, decision, condition="name_swap", ok=True, rep=1):
    return {
        "provider": "openai",
        "model": "gpt-6-luna-2026-10-01",
        "condition": condition,
        "resume_id": str(resume),
        "name": name,
        "race": race,
        "gender": gender,
        "repeat": str(rep),
        "score": str(score) if ok else "",
        "decision": decision if ok else "",
        "parse_ok": "true" if ok else "false",
    }


def dataset(repeats=2):
    """Resume 1 spreads groups 60/70/80/90; resume 2 is flat at 50."""
    plan = {
        1: {
            ("Black", "F"): (60, "REJECT"),
            ("Black", "M"): (70, "ADVANCE"),
            ("white", "F"): (80, "ADVANCE"),
            ("white", "M"): (90, "ADVANCE"),
        },
        2: {
            ("Black", "F"): (50, "REJECT"),
            ("Black", "M"): (50, "REJECT"),
            ("white", "F"): (50, "REJECT"),
            ("white", "M"): (50, "ADVANCE"),
        },
    }
    low = {1: 40, 2: 30}
    rows = []
    for resume, groups in plan.items():
        for rep in range(1, repeats + 1):
            for (race, gender), (score, decision) in groups.items():
                for name in GROUP_NAMES[(race, gender)]:
                    rows.append(row(resume, name, race, gender, score, decision, rep=rep))
                    if name in DEGREE_NAMES:
                        rows.append(
                            row(
                                resume,
                                name,
                                race,
                                gender,
                                low[resume],
                                "REJECT",
                                condition="degree_swap",
                                rep=rep,
                            )
                        )
    return rows


def test_point_estimates_by_hand():
    m = metrics.compute(dataset(), "openai", DEGREE_NAMES, samples=500)
    gaps = [m.score_gap[g].estimate for g in metrics.GROUPS]
    assert gaps == pytest.approx([-7.5, -2.5, 2.5, 7.5])
    assert sum(gaps) == pytest.approx(0)
    rates = [m.selection_rate[g].estimate for g in metrics.GROUPS]
    assert rates == pytest.approx([0.0, 0.5, 0.5, 1.0])
    assert m.impact_ratio_by_group == pytest.approx(
        {"Black F": 0.0, "Black M": 0.5, "white F": 0.5, "white M": 1.0}
    )
    assert m.impact_ratio.estimate == pytest.approx(0.0)
    assert m.name_spread.estimate == pytest.approx(15.0)
    assert m.degree_gap.estimate == pytest.approx(27.5)
    assert m.relative_effect.estimate == pytest.approx(15 / 27.5)
    assert m.highest_score_group == "white M"
    assert m.highest_rate_group == "white M"
    assert m.resumes == 2
    assert m.models_seen == ["gpt-6-luna-2026-10-01"]


def test_failed_calls_are_left_out():
    rows = dataset()
    rows.append(row(1, "Ann", "Black", "F", 0, "", ok=False, rep=3))
    m = metrics.compute(rows, "openai", DEGREE_NAMES, samples=200)
    assert m.failed_calls == 1
    assert m.score_gap["Black F"].estimate == pytest.approx(-7.5)


def test_bootstrap_is_reproducible_and_brackets_the_estimate():
    a = metrics.compute(dataset(), "openai", DEGREE_NAMES, samples=2000, seed=1)
    b = metrics.compute(dataset(), "openai", DEGREE_NAMES, samples=2000, seed=1)
    assert a.score_gap["white M"] == b.score_gap["white M"]
    ci = a.score_gap["white M"]
    # With two resumes the only resample means are 0, 7.5 and 15.
    assert ci.low == pytest.approx(0.0) and ci.high == pytest.approx(15.0)
    assert ci.low <= ci.estimate <= ci.high


def test_bootstrap_resamples_resumes_not_calls():
    """More repeats of the same resumes must not narrow the interval."""
    two = metrics.compute(dataset(repeats=2), "openai", DEGREE_NAMES, samples=2000, seed=3)
    ten = metrics.compute(dataset(repeats=10), "openai", DEGREE_NAMES, samples=2000, seed=3)
    for g in metrics.GROUPS:
        assert two.score_gap[g].low == pytest.approx(ten.score_gap[g].low)
        assert two.score_gap[g].high == pytest.approx(ten.score_gap[g].high)


def test_identical_resumes_give_zero_width_interval():
    rows = [r for r in dataset() if r["resume_id"] == "1"]
    rows += [dict(r, resume_id="3") for r in rows]
    m = metrics.compute(rows, "openai", DEGREE_NAMES, samples=500)
    assert m.score_gap["Black F"].low == m.score_gap["Black F"].high == pytest.approx(-15)


def test_nonpositive_degree_gap_gives_infinite_relative_effect():
    rows = [dict(r, score="95") if r["condition"] == "degree_swap" else r for r in dataset()]
    m = metrics.compute(rows, "openai", DEGREE_NAMES, samples=200)
    assert m.degree_gap.estimate < 0
    assert math.isinf(m.relative_effect.estimate)


def test_statistics_vectorized_matches_loop():
    rows = dataset()
    cells = metrics.build_cells(rows, DEGREE_NAMES)
    idx = np.array([[0, 0], [1, 1], [0, 1]])
    stats = metrics.statistics(cells, idx)
    assert stats["gap"][0] == pytest.approx([-15, -5, 5, 15])
    assert stats["gap"][1] == pytest.approx([0, 0, 0, 0])
    assert stats["rate"][1] == pytest.approx([0, 0, 0, 1])
