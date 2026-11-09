"""Smoke tests of the command line on the real materials, with the offline fake provider."""

import json

from name_audit import cli, harness


def test_materials_pass_quality_check(capsys):
    cli.main(["quality-check"])  # exits non-zero on any failed check
    assert "FAIL" not in capsys.readouterr().out


def test_full_offline_pipeline(tmp_path, capsys):
    pilot = tmp_path / "pilot"
    cli.main(["run", "pilot", "--out", str(pilot), "--fake"])
    assert len(harness.read_results(pilot / "results.csv")) == 2 * 40 * 2
    cli.main(["pilot-report", str(pilot), "--write", str(tmp_path / "pilot.md")])
    assert "Pilot gate" in (tmp_path / "pilot.md").read_text()

    main = tmp_path / "main"
    cli.main(["run", "main", "--out", str(main), "--fake"])
    rows = harness.read_results(main / "results.csv")
    assert len(rows) == 2 * (960 + 320)
    cli.main(["analyze", str(main), "--samples", "200"])
    metrics = json.loads((main / "metrics.json").read_text())
    assert set(metrics["models"]) == {"openai", "gemini"}
    assert metrics["ending"] in {"perception problem", "mixed verdict", "real problem"}

    cli.main(["probe", str(main), "--fake"])
    summary = json.loads((main / "probe" / "probe_summary.json").read_text())
    assert summary["openai"]["harness_n"] == 24 and summary["openai"]["contrast_n"] == 24
    capsys.readouterr()


def test_rerun_with_a_different_plan_is_refused(tmp_path):
    out = tmp_path / "pilot"
    cli.main(["run", "pilot", "--out", str(out), "--fake", "--resumes", "1,2"])
    try:
        cli.main(["run", "pilot", "--out", str(out), "--fake", "--resumes", "1,3"])
    except SystemExit as exc:
        assert "differs" in str(exc)
    else:
        raise AssertionError("expected the second run to be refused")
