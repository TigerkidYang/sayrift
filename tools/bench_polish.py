"""Benchmark text models on the dictation-cleanup prompt: rule checks, latency, cost.

Runs every case in evals/polish/cases.jsonl through each model using the app's own
prompt builder (local_typeless.prompts) and request presets (local_typeless.models).

Usage (from repo root):
    uv run python tools/bench_polish.py                               # default candidates
    uv run python tools/bench_polish.py --models openai/gpt-6-luna --show
    uv run python tools/bench_polish.py --only zh_question zh_injection --repeat 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from local_typeless import prompts
from local_typeless.models import CHAT_PRESETS, chat_extra
from local_typeless.openrouter import OpenRouterClient, OpenRouterError

DEFAULT_MODELS = [m for m in CHAT_PRESETS if m != "google/gemini-3.8-flash"]


@dataclass
class Run:
    model: str
    case: str
    ok: bool
    text: str = ""
    ttft_s: float | None = None
    latency_s: float | None = None
    cost_usd: float | None = None
    provider: str | None = None
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def check(case: dict, out: str) -> list[str]:
    fails = []
    for s in case.get("must", []):
        if s not in out:
            fails.append(f"missing {s!r}")
    for group in case.get("must_any", []):
        if not any(s in out for s in group):
            fails.append(f"missing one of {group}")
    for s in case.get("must_not", []):
        if s in out:
            fails.append(f"contains {s!r}")
    ratio = case.get("max_ratio")
    if ratio and len(out) > ratio * max(len(case["transcript"]), 1):
        fails.append(f"too long ({len(out)} vs {len(case['transcript'])} chars)")
    if "max_chars" in case and len(out) > case["max_chars"]:
        fails.append(f"expected (near) empty, got {len(out)} chars")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if case.get("min_lines") and len(lines) < case["min_lines"]:
        fails.append(f"{len(lines)} lines < {case['min_lines']}")
    return fails


def run_case(client: OpenRouterClient, model: str, case: dict) -> Run:
    ctx = prompts.Context(**case.get("context", {}))
    messages = prompts.dictation_messages(case["transcript"], ctx)
    try:
        res = client.chat(messages, model, max_tokens=max(256, 4 * len(case["transcript"])), extra=chat_extra(model))
    except OpenRouterError as e:
        return Run(model, case["id"], False, error=str(e)[:300])
    fails = check(case, res.text)
    return Run(model, case["id"], not fails, res.text, res.ttft_s, res.latency_s, res.cost_usd, res.provider, fails)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=Path, default=Path("evals/polish/cases.jsonl"))
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    ap.add_argument("--only", nargs="*", help="subset of case ids")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--show", action="store_true", help="print every output")
    ap.add_argument("--out", type=Path, help="write raw runs as JSON")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Chinese output through pipes on Windows

    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    jobs = [(m, c) for _ in range(args.repeat) for m in args.models for c in cases]

    with OpenRouterClient() as client:
        client.warm_up()
        with ThreadPoolExecutor(args.workers) as pool:
            runs = list(pool.map(lambda j: run_case(client, *j), jobs))

    print(f"\n{'model':34} {'pass':>7} {'err':>4} {'ttft p50':>9} {'total p50':>9} {'total p90':>9} {'$/1k calls':>10}")
    table = []
    for m in args.models:
        rs = [r for r in runs if r.model == m]
        done = [r for r in rs if r.error is None]
        ttft = [r.ttft_s for r in done if r.ttft_s is not None]
        tot = sorted(r.latency_s for r in done if r.latency_s is not None)
        cost = [r.cost_usd for r in done if r.cost_usd is not None]
        p90 = tot[min(len(tot) - 1, int(0.9 * len(tot)))] if tot else float("nan")
        table.append(
            (
                -sum(r.ok for r in rs),
                m,
                f"{sum(r.ok for r in rs)}/{len(rs)}",
                len(rs) - len(done),
                statistics.median(ttft) if ttft else float("nan"),
                statistics.median(tot) if tot else float("nan"),
                p90,
                1000 * statistics.mean(cost) if cost else float("nan"),
            )
        )
    for _, m, passed, err, ttft, p50, p90, cost in sorted(table):
        print(f"{m:34} {passed:>7} {err:>4} {ttft:9.2f} {p50:9.2f} {p90:9.2f} {cost:10.3f}")

    print("\nFailures:")
    for r in runs:
        if not r.ok:
            detail = r.error or "; ".join(r.failures)
            print(f"  {r.model:34} {r.case:22} {detail}")
            if r.text and not args.show:
                print(f"  {'':34} {'':22} -> {r.text!r}")

    if args.show:
        for c in cases:
            print(f"\n=== {c['id']}\n  IN : {c['transcript']}\n  EXP: {c.get('expect', '')!r}")
            for r in runs:
                if r.case == c["id"]:
                    mark = "ok " if r.ok else "BAD"
                    print(f"  {mark} {r.model:32} {r.text!r}")

    if args.out:
        args.out.write_text(json.dumps([asdict(r) for r in runs], ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
