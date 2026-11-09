import csv

from name_audit import pilot
from name_audit.harness import CSV_COLUMNS


def write(run_dir, rows):
    run_dir.mkdir()
    with (run_dir / "results.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            w.writerow(
                {c: "" for c in CSV_COLUMNS}
                | {
                    "run_id": f"r{i:04d}",
                    "condition": "pilot",
                    "model": "m",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "parse_ok": "true",
                }
                | r
            )


def rows_for(provider, resume, high, low):
    out = []
    for level, (score, decision) in (("high", high), ("low", low)):
        out.append(
            {
                "provider": provider,
                "resume_id": resume,
                "degree_level": level,
                "score": score,
                "decision": decision,
            }
        )
    return out


def test_report_flags_and_floor(tmp_path):
    rows = []
    for p in ("openai", "gemini"):
        rows += rows_for(p, 1, (90, "ADVANCE"), (85, "ADVANCE"))  # always advance
        rows += rows_for(p, 2, (20, "REJECT"), (10, "REJECT"))  # always reject
        rows += rows_for(p, 3, (70, "ADVANCE"), (45, "REJECT"))
    write(tmp_path / "p1", rows)
    rep = pilot.report([tmp_path / "p1"])
    assert rep.always_advance == [1] and rep.always_reject == [2]
    m = {x.provider: x for x in rep.models}["openai"]
    assert m.degree_gap == (5 + 10 + 25) / 3
    assert m.passes_degree_floor
    assert m.advance_rate_high == 2 / 3 and m.in_advance_range
    assert rep.passes and rep.meets_targets  # two uniform resumes are within the limit
    assert "Always ADVANCE" in pilot.render(rep)
    assert "Degree floor (the hard rule): PASS" in pilot.render(rep)


def test_later_run_replaces_repiloted_resumes(tmp_path):
    first = []
    for p in ("openai", "gemini"):
        first += rows_for(p, 1, (90, "ADVANCE"), (88, "ADVANCE"))
        first += rows_for(p, 2, (70, "ADVANCE"), (40, "REJECT"))
    write(tmp_path / "p1", first)
    second = []
    for p in ("openai", "gemini"):
        second += rows_for(p, 1, (66, "ADVANCE"), (35, "REJECT"))
    write(tmp_path / "p2", second)
    rep = pilot.report([tmp_path / "p1", tmp_path / "p2"])
    assert rep.always_advance == [] and rep.always_reject == []
    assert all(m.degree_gap == (31 + 30) / 2 for m in rep.models)
    assert all(m.passes_degree_floor for m in rep.models)


def test_floor_fails_below_ten(tmp_path):
    rows = []
    for p in ("openai", "gemini"):
        rows += rows_for(p, 1, (70, "ADVANCE"), (61, "REJECT"))
    write(tmp_path / "p1", rows)
    rep = pilot.report([tmp_path / "p1"])
    assert not any(m.passes_degree_floor for m in rep.models)
    assert not rep.passes


def test_too_many_uniform_resumes_fail(tmp_path):
    rows = []
    for p in ("openai", "gemini"):
        for rid in range(1, 4):
            rows += rows_for(p, rid, (90, "ADVANCE"), (75, "ADVANCE"))
        for rid in range(4, 7):
            rows += rows_for(p, rid, (40, "REJECT"), (25, "REJECT"))
    write(tmp_path / "p1", rows)
    rep = pilot.report([tmp_path / "p1"])
    assert all(m.passes_degree_floor and m.in_advance_range for m in rep.models)
    assert len(rep.always_advance) + len(rep.always_reject) == 6
    assert rep.passes and not rep.meets_targets


def test_advance_rate_out_of_range_fails(tmp_path):
    rows = []
    for p in ("openai", "gemini"):
        for rid in range(1, 5):
            rows += rows_for(p, rid, (80, "ADVANCE"), (60, "REJECT"))
    write(tmp_path / "p1", rows)
    rep = pilot.report([tmp_path / "p1"])
    assert rep.overall_advance_high == 1.0
    assert rep.passes and not rep.meets_targets
