import json

from name_audit import probe
from name_audit.harness import plan_calls, run_screening
from name_audit.providers.fake import FakeProvider


def test_probe_plan_and_run(materials, tmp_path):
    run_dir = tmp_path / "main"
    providers = {"openai": FakeProvider(name="openai"), "gemini": FakeProvider(name="gemini")}
    plan = plan_calls(materials, "main", list(providers))
    run_screening(plan, providers, materials, run_dir)

    specs = probe.plan_probes(materials, run_dir, ["openai", "gemini"], per_name=2)
    for p in ("openai", "gemini"):
        mine = [s for s in specs if s.provider == p]
        assert sum(s.kind == "harness" for s in mine) == 2 * len(materials.names)
        assert sum(s.kind == "contrast" for s in mine) == 2 * len(materials.names)
    contrast = next(s for s in specs if s.kind == "contrast")
    a, b = contrast.names
    assert a != b and materials.name(a).group != materials.name(b).group
    assert "APPLICATION A:" in contrast.transcript and "APPLICATION B:" in contrast.transcript
    assert a in contrast.transcript and b in contrast.transcript
    harness_spec = next(s for s in specs if s.kind == "harness")
    assert "ASSISTANT:\n{" in harness_spec.transcript
    assert harness_spec.provider == "openai" or harness_spec.provider == "gemini"

    def reply(system, user):
        value = 90 if "APPLICATION A:" in user else 20
        return json.dumps({"probability": value, "reason": "Scripted."})

    probers = {p: FakeProvider(name=p, reply=reply) for p in providers}
    out = tmp_path / "probe"
    attempted, failed, _, _ = probe.run_probes(specs, probers, out)
    assert attempted == len(specs) and failed == 0
    summary = probe.summarize(out)
    assert summary["openai"]["harness"] == 20 and summary["openai"]["contrast"] == 90
    assert summary["gemini"]["harness_n"] == 2 * len(materials.names)


def test_harness_transcripts_use_own_model_calls(materials, tmp_path):
    run_dir = tmp_path / "main"
    providers = {"openai": FakeProvider(name="openai"), "gemini": FakeProvider(name="gemini")}
    run_screening(plan_calls(materials, "main", list(providers)), providers, materials, run_dir)
    from name_audit.harness import read_results

    by_id = {r["run_id"]: r for r in read_results(run_dir / "results.csv")}
    for spec in probe.plan_probes(materials, run_dir, ["openai", "gemini"]):
        assert all(by_id[rid]["provider"] == spec.provider for rid in spec.source_run_ids)
