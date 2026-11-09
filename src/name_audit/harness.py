"""Plan screening calls, run them, and record one CSV row plus one raw file per call."""

import csv
import json
import random
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import COMPANY, PILOT_NAME, PRICES, REPEATS, SEED
from .materials import Materials
from .parse import ParseError, parse_screening
from .prompt import SCREENING_SCHEMA, system_prompt, user_prompt
from .providers import Provider, ProviderError

CSV_COLUMNS = [
    "run_id",
    "timestamp_utc",
    "provider",
    "model",
    "condition",
    "resume_id",
    "name",
    "race",
    "gender",
    "degree_level",
    "repeat",
    "score",
    "decision",
    "reason",
    "input_tokens",
    "output_tokens",
    "parse_ok",
]
PLAN_COLUMNS = [
    "run_id",
    "provider",
    "condition",
    "resume_id",
    "name",
    "race",
    "gender",
    "degree_level",
    "repeat",
]


@dataclass(frozen=True)
class CallSpec:
    run_id: str
    provider: str
    condition: str
    resume_id: int
    name: str
    race: str
    gender: str
    degree_level: str
    repeat: int


def plan_calls(
    materials: Materials,
    stage: str,
    providers: Iterable[str],
    resume_ids: Iterable[int] | None = None,
    seed: int = SEED,
) -> list[CallSpec]:
    """Every call for a stage, in a seeded random order so no group runs in one block.

    stage "pilot": every resume once with the fixed pilot name at both degree levels.
    stage "main": the name swap (12 names, high degree) and the degree swap
    (one name per group, low degree), each repeated REPEATS times.
    """
    ids = sorted(resume_ids) if resume_ids is not None else sorted(materials.resumes)
    unknown = set(ids) - set(materials.resumes)
    if unknown:
        raise ValueError(f"unknown resume ids: {sorted(unknown)}")
    cells: list[tuple[str, str, int, Any, str, int]] = []
    for provider in providers:
        for rid in ids:
            if stage == "pilot":
                pilot = materials.name(PILOT_NAME)
                for level in ("high", "low"):
                    cells.append((provider, "pilot", rid, pilot, level, 1))
            elif stage == "main":
                for repeat in range(1, REPEATS + 1):
                    for name in materials.names:
                        cells.append((provider, "name_swap", rid, name, "high", repeat))
                    for name in materials.names:
                        if name.degree_swap:
                            cells.append((provider, "degree_swap", rid, name, "low", repeat))
            else:
                raise ValueError(f"unknown stage: {stage}")
    random.Random(seed).shuffle(cells)
    return [
        CallSpec(
            run_id=f"r{i:04d}",
            provider=provider,
            condition=condition,
            resume_id=rid,
            name=name.name,
            race=name.race,
            gender=name.gender,
            degree_level=level,
            repeat=repeat,
        )
        for i, (provider, condition, rid, name, level, repeat) in enumerate(cells, start=1)
    ]


def write_plan(path: Path, plan: list[CallSpec]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PLAN_COLUMNS)
        writer.writeheader()
        for spec in plan:
            writer.writerow(asdict(spec))


def read_plan(path: Path) -> list[CallSpec]:
    with path.open() as fh:
        return [
            CallSpec(
                run_id=row["run_id"],
                provider=row["provider"],
                condition=row["condition"],
                resume_id=int(row["resume_id"]),
                name=row["name"],
                race=row["race"],
                gender=row["gender"],
                degree_level=row["degree_level"],
                repeat=int(row["repeat"]),
            )
            for row in csv.DictReader(fh)
        ]


def read_results(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open() as fh:
        return list(csv.DictReader(fh))


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES.get(provider, (0.0, 0.0))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


@dataclass
class Outcome:
    """The result of one logical call: up to two attempts, the second only on failure."""

    parsed: tuple | None
    attempts: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return self.parsed is not None

    @property
    def input_tokens(self) -> int:
        return sum(a["input_tokens"] for a in self.attempts)

    @property
    def output_tokens(self) -> int:
        return sum(a["output_tokens"] for a in self.attempts)

    @property
    def model(self) -> str:
        for attempt in reversed(self.attempts):
            if attempt["model"]:
                return attempt["model"]
        return ""

    @property
    def text(self) -> str:
        return self.attempts[-1]["text"] if self.attempts else ""


def call_with_retry(
    provider: Provider,
    system: str,
    user: str,
    schema: dict[str, Any],
    parser: Callable[[str], tuple],
    max_attempts: int = 2,
) -> Outcome:
    """Call once; if the reply fails to arrive or to parse, call one more time."""
    attempts: list[dict[str, Any]] = []
    for _ in range(max_attempts):
        record: dict[str, Any] = {
            "timestamp_utc": now_utc(),
            "model": "",
            "text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "error": None,
            "response": None,
        }
        try:
            completion = provider.complete(system, user, schema)
        except ProviderError as exc:
            record["error"] = f"provider: {exc}"
            attempts.append(record)
            continue
        record.update(
            model=completion.model,
            text=completion.text,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            response=completion.raw,
        )
        try:
            parsed = parser(completion.text)
        except ParseError as exc:
            record["error"] = f"parse: {exc}"
            attempts.append(record)
            continue
        attempts.append(record)
        return Outcome(parsed=parsed, attempts=attempts)
    return Outcome(parsed=None, attempts=attempts)


def screening_prompts(materials: Materials, spec: CallSpec) -> tuple[str, str]:
    resume = materials.fill(spec.resume_id, materials.name(spec.name), spec.degree_level)
    return system_prompt(COMPANY), user_prompt(materials.job_posting, resume)


def result_row(spec: CallSpec, outcome: Outcome) -> dict[str, Any]:
    score, decision, reason = outcome.parsed if outcome.ok else ("", "", "")
    return {
        "run_id": spec.run_id,
        "timestamp_utc": outcome.attempts[-1]["timestamp_utc"],
        "provider": spec.provider,
        "model": outcome.model,
        "condition": spec.condition,
        "resume_id": spec.resume_id,
        "name": spec.name,
        "race": spec.race,
        "gender": spec.gender,
        "degree_level": spec.degree_level,
        "repeat": spec.repeat,
        "score": score,
        "decision": decision,
        "reason": reason,
        "input_tokens": outcome.input_tokens,
        "output_tokens": outcome.output_tokens,
        "parse_ok": "true" if outcome.ok else "false",
    }


class RunWriter:
    """Thread-safe appender for results.csv and the per-call raw files."""

    def __init__(self, out_dir: Path, columns: list[str], raw_dir: str = "raw"):
        self.out_dir = out_dir
        self.raw_dir = out_dir / raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.columns = columns
        self.lock = threading.Lock()

    def write(self, results_name: str, row: dict[str, Any], raw: dict[str, Any]) -> None:
        with self.lock:
            (self.raw_dir / f"{row['run_id']}.json").write_text(json.dumps(raw, indent=1) + "\n")
            path = self.out_dir / results_name
            new = not path.exists()
            with path.open("a", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=self.columns)
                if new:
                    writer.writeheader()
                writer.writerow(row)


@dataclass
class RunSummary:
    attempted: int
    failed: int
    skipped: int
    spend: float
    stopped_for_budget: bool


def execute(
    jobs: list[tuple[str, str, Callable[[], tuple[str, str, Outcome]]]],
    finish: Callable[[str, Outcome], None],
    max_spend: float | None,
    already_spent: float,
    workers: int,
    log: Callable[[str], None] = print,
) -> tuple[int, int, float, bool]:
    """Run jobs with bounded concurrency, stopping new submissions once the budget is hit.

    Each job is (job_id, provider_name, fn). fn returns (job_id, provider_name, outcome).
    """
    spent = already_spent
    attempted = failed = 0
    stopped = False
    pending: set[Future] = set()
    total = len(jobs)

    def drain(done: set[Future]) -> None:
        nonlocal spent, attempted, failed
        for future in done:
            job_id, provider_name, outcome = future.result()
            finish(job_id, outcome)
            spent += cost(provider_name, outcome.input_tokens, outcome.output_tokens)
            attempted += 1
            failed += 0 if outcome.ok else 1
            if attempted % 25 == 0 or attempted == total:
                log(f"{attempted}/{total} calls, {failed} failed, ${spent:.4f} spent")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _job_id, _provider_name, fn in jobs:
            if max_spend is not None and spent >= max_spend:
                stopped = True
                break
            pending.add(pool.submit(fn))
            if len(pending) >= workers:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                drain(done)
        done, _ = wait(pending)
        drain(done)
    return attempted, failed, spent, stopped


def run_screening(
    plan: list[CallSpec],
    providers: dict[str, Provider],
    materials: Materials,
    out_dir: Path,
    workers: int = 8,
    max_spend: float | None = None,
    log: Callable[[str], None] = print,
) -> RunSummary:
    """Run every planned call that is not already in results.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    previous = read_results(out_dir / "results.csv")
    done_ids = {row["run_id"] for row in previous}
    already_spent = sum(
        cost(row["provider"], int(row["input_tokens"]), int(row["output_tokens"]))
        for row in previous
    )
    todo = [spec for spec in plan if spec.run_id not in done_ids]
    writer = RunWriter(out_dir, CSV_COLUMNS)
    by_id = {spec.run_id: spec for spec in todo}

    def make_job(spec: CallSpec):
        def job():
            system, user = screening_prompts(materials, spec)
            outcome = call_with_retry(
                providers[spec.provider], system, user, SCREENING_SCHEMA, parse_screening
            )
            return spec.run_id, spec.provider, outcome

        return spec.run_id, spec.provider, job

    def finish(run_id: str, outcome: Outcome) -> None:
        spec = by_id[run_id]
        raw = {
            "run_id": run_id,
            "provider": spec.provider,
            "requested_model": providers[spec.provider].model,
            "attempts": outcome.attempts,
        }
        writer.write("results.csv", result_row(spec, outcome), raw)

    attempted, failed, spent, stopped = execute(
        [make_job(spec) for spec in todo], finish, max_spend, already_spent, workers, log
    )
    return RunSummary(
        attempted=attempted,
        failed=failed,
        skipped=len(plan) - len(todo),
        spend=spent,
        stopped_for_budget=stopped,
    )
