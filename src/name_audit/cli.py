"""Command line entry point: name-audit <command>."""

import argparse
import json
import math
import sys
from pathlib import Path

from . import decision, harness, metrics, pilot, probe, quality
from .config import COMPANY, MODELS
from .keys import read_key
from .materials import default as load_materials
from .prompt import system_prompt, user_prompt
from .providers import Provider
from .providers.fake import FakeProvider


def make_providers(names: list[str], env_file: Path | None, fake: bool) -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    for name in names:
        if fake:
            providers[name] = FakeProvider(name=name, model=MODELS[name])
            continue
        key = read_key(name, env_file)
        if name == "openai":
            from .providers.openai_client import OpenAIProvider

            providers[name] = OpenAIProvider(MODELS[name], key)
        elif name == "gemini":
            from .providers.gemini_client import GeminiProvider

            providers[name] = GeminiProvider(MODELS[name], key)
        else:
            raise SystemExit(f"unknown provider: {name}")
    return providers


def parse_ids(text: str | None) -> list[int] | None:
    return [int(x) for x in text.split(",")] if text else None


def cmd_models(args: argparse.Namespace) -> None:
    """List model ids with each provider's free model list endpoint."""
    for name, provider in make_providers(args.providers, args.env_file, False).items():
        listed = provider.list_models()
        status = "listed" if MODELS[name] in listed else "NOT LISTED"
        print(f"{name}: {MODELS[name]} {status}")
        if args.verbose:
            print("  " + "\n  ".join(listed))


def cmd_render(args: argparse.Namespace) -> None:
    m = load_materials()
    resume = m.fill(args.resume, m.name(args.name), args.degree)
    if args.resume_only:
        print(resume)
        return
    print("SYSTEM:\n" + system_prompt(COMPANY) + "\n\nUSER:\n" + user_prompt(m.job_posting, resume))


def cmd_plan(args: argparse.Namespace) -> None:
    m = load_materials()
    plan = harness.plan_calls(m, args.stage, args.providers, parse_ids(args.resumes))
    by_condition: dict[str, int] = {}
    for spec in plan:
        by_condition[f"{spec.provider} {spec.condition}"] = (
            by_condition.get(f"{spec.provider} {spec.condition}", 0) + 1
        )
    for key, count in sorted(by_condition.items()):
        print(f"{key}: {count}")
    print(f"total: {len(plan)}")


def cmd_run(args: argparse.Namespace) -> None:
    m = load_materials()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    plan = harness.plan_calls(m, args.stage, args.providers, parse_ids(args.resumes))
    plan_path = out / "plan.csv"
    if plan_path.exists():
        if harness.read_plan(plan_path) != plan:
            raise SystemExit(f"{plan_path} differs from this command's plan; use a new --out")
    else:
        harness.write_plan(plan_path, plan)
    providers = make_providers(args.providers, args.env_file, args.fake)
    summary = harness.run_screening(
        plan, providers, m, out, workers=args.workers, max_spend=args.max_spend
    )
    print(json.dumps(summary.__dict__, indent=2))
    if summary.stopped_for_budget:
        sys.exit(2)


def cmd_pilot_report(args: argparse.Namespace) -> None:
    text = pilot.render(pilot.report(args.runs))
    print(text)
    if args.write:
        args.write.write_text(text)


def _fmt(interval: metrics.Interval, pct: bool = False) -> str:
    def f(x: float) -> str:
        if math.isinf(x):
            return "inf"
        return f"{x:.1%}" if pct else f"{x:.3f}"

    return f"{f(interval.estimate)} [{f(interval.low)}, {f(interval.high)}]"


def cmd_analyze(args: argparse.Namespace) -> None:
    m = load_materials()
    rows = harness.read_results(args.run / "results.csv")
    degree_names = {n.name for n in m.names if n.degree_swap}
    results, endings, lines = {}, {}, ["# Results", ""]
    for provider in sorted({r["provider"] for r in rows}):
        mm = metrics.compute(rows, provider, degree_names, samples=args.samples)
        verdict = decision.ending(mm.impact_ratio.estimate, mm.relative_effect.estimate)
        endings[provider] = verdict
        results[provider] = mm.as_dict() | {"ending": verdict}
        lines += [
            f"## {', '.join(mm.models_seen) or provider}",
            "",
            f"Resumes: {mm.resumes}. Calls: {mm.calls}. Failed after retry: {mm.failed_calls}.",
            "",
            "| group | score gap | selection rate | impact ratio |",
            "|---|---|---|---|",
        ]
        for g in metrics.GROUPS:
            lines.append(
                f"| {g} | {_fmt(mm.score_gap[g])} | {_fmt(mm.selection_rate[g], True)} "
                f"| {mm.impact_ratio_by_group[g]:.3f} |"
            )
        lines += [
            "",
            f"- Highest score gap: {mm.highest_score_group}. "
            f"Highest selection rate: {mm.highest_rate_group}.",
            f"- Impact ratio (lowest over highest): {_fmt(mm.impact_ratio)}",
            f"- Widest name gap: {_fmt(mm.name_spread)} points",
            f"- Degree gap: {_fmt(mm.degree_gap)} points",
            f"- Relative effect: {_fmt(mm.relative_effect)}",
            f"- Ending for this model: {verdict}",
            "",
        ]
    final = decision.overall(endings.values())
    lines.append(f"Study ending (worse of the models): {final}")
    out = {"models": results, "ending": final}
    (args.run / "metrics.json").write_text(json.dumps(out, indent=2) + "\n")
    (args.run / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_probe(args: argparse.Namespace) -> None:
    m = load_materials()
    out = args.out or args.run / "probe"
    out.mkdir(parents=True, exist_ok=True)
    specs = probe.plan_probes(m, args.run, args.providers)
    probe.write_plan(out / "probe_plan.csv", specs)
    providers = make_providers(args.providers, args.env_file, args.fake)
    attempted, failed, spent, stopped = probe.run_probes(
        specs, providers, out, workers=args.workers, max_spend=args.max_spend
    )
    summary = probe.summarize(out)
    (out / "probe_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                "attempted": attempted,
                "failed": failed,
                "spend": spent,
                "stopped_for_budget": stopped,
                "summary": summary,
            },
            indent=2,
        )
    )
    if stopped:
        sys.exit(2)


def cmd_quality(args: argparse.Namespace) -> None:
    checks = quality.run(load_materials())
    text = quality.render(checks)
    print(text)
    if args.write:
        args.write.write_text(text)
    if not all(c.passed for c in checks):
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="name-audit", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_provider_args(p: argparse.ArgumentParser, keys: bool = True) -> None:
        p.add_argument(
            "--providers",
            type=lambda s: s.split(","),
            default=list(MODELS),
            help="comma separated: openai,gemini",
        )
        if keys:
            p.add_argument(
                "--env-file",
                type=Path,
                default=None,
                help="file holding OPENAI_API_KEY and GEMINI_API_KEY lines",
            )

    def add_run_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workers", type=int, default=8)
        p.add_argument("--max-spend", type=float, default=None, help="stop at this many USD")
        p.add_argument("--fake", action="store_true", help="use the offline fake provider")

    p = sub.add_parser("models", help="confirm model ids with the model list endpoints")
    add_provider_args(p)
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("render", help="print one filled prompt")
    p.add_argument("--resume", type=int, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--degree", choices=["high", "low"], default="high")
    p.add_argument("--resume-only", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("plan", help="count the calls a stage would make")
    p.add_argument("stage", choices=["pilot", "main"])
    p.add_argument("--resumes", help="comma separated resume ids (default: all)")
    add_provider_args(p, keys=False)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("run", help="run the pilot or main screening calls")
    p.add_argument("stage", choices=["pilot", "main"])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--resumes", help="comma separated resume ids (default: all)")
    add_provider_args(p)
    add_run_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("pilot-report", help="degree floor, ADVANCE aim and uniform resumes")
    p.add_argument("runs", type=Path, nargs="+", help="pilot run folders, later ones win")
    p.add_argument("--write", type=Path, default=None)
    p.set_defaults(func=cmd_pilot_report)

    p = sub.add_parser("analyze", help="metrics, intervals and the decision rule")
    p.add_argument("run", type=Path)
    p.add_argument("--samples", type=int, default=metrics.BOOTSTRAP_SAMPLES)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("probe", help="run the eval-awareness probe on a finished main run")
    p.add_argument("run", type=Path)
    p.add_argument("--out", type=Path, default=None)
    add_provider_args(p)
    add_run_args(p)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("quality-check", help="mechanical checks on the materials (no API calls)")
    p.add_argument("--write", type=Path, default=None)
    p.set_defaults(func=cmd_quality)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
