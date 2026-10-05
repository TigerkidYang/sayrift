"""Benchmark models on Ask anything: routing (replace / insert / answer), rule checks, latency.

Runs every case in evals/ask/cases.jsonl through pipeline.ask_text with the app's own prompt,
response format and request presets.

Usage (from repo root):
    uv run python tools/bench_ask.py                                  # default Ask model
    uv run python tools/bench_ask.py --models deepseek/deepseek-v4.1-flash openai/gpt-5.6-luna --repeat 2
    uv run python tools/bench_ask.py --only formal_rewrite --show
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from local_typeless import pipeline, prompts
from local_typeless.config import Config
from local_typeless.openrouter import OpenRouterClient, OpenRouterError


def check(case: dict, action: str, out: str) -> list[str]:
    fails = []
    if action != case["action"]:
        fails.append(f"action {action} != {case['action']}")
    fails += [f"missing {s!r}" for s in case.get("must", []) if s not in out]
    fails += [f"missing one of {g}" for g in case.get("must_any", []) if not any(s in out for s in g)]
    fails += [f"contains {s!r}" for s in case.get("must_not", []) if s in out]
    if case.get("min_lines") and len([ln for ln in out.splitlines() if ln.strip()]) < case["min_lines"]:
        fails.append(f"fewer than {case['min_lines']} lines")
    if case.get("max_ratio") and len(out) > case["max_ratio"] * len(case.get("selection", "")):
        fails.append(f"not shorter ({len(out)} vs {len(case.get('selection', ''))} chars)")
    return fails


def run_case(client: OpenRouterClient, cfg: Config, model: str, case: dict) -> dict:
    ctx = prompts.Context(**case.get("context", {}))
    try:
        res = pipeline.ask_text(client, cfg, case["spoken"], ctx, selection=case.get("selection"))
    except OpenRouterError as e:
        return {"model": model, "case": case["id"], "ok": False, "error": str(e)[:200]}
    fails = check(case, res.action, res.text)
    return {
        "model": model,
        "case": case["id"],
        "ok": not fails,
        "action": res.action,
        "text": res.text,
        "latency": res.llm.latency_s if res.llm else None,
        "failures": fails,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=Path, default=Path("evals/ask/cases.jsonl"))
    ap.add_argument("--models", nargs="*", default=[Config().ask.model])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    configs = {}
    for m in args.models:
        cfg = deepcopy(Config())
        cfg.ask.model, cfg.ask.fallback_model = m, None
        configs[m] = cfg
    jobs = [(m, c) for _ in range(args.repeat) for m in args.models for c in cases]
    with OpenRouterClient() as client:
        client.warm_up()
        with ThreadPoolExecutor(args.workers) as pool:
            runs = list(pool.map(lambda j: run_case(client, configs[j[0]], *j), jobs))

    print(f"\n{'model':34} {'pass':>7} {'p50 s':>6} {'max s':>6}")
    for m in args.models:
        rs = [r for r in runs if r["model"] == m]
        lat = [r["latency"] for r in rs if r.get("latency")]
        p50 = statistics.median(lat) if lat else float("nan")
        mx = max(lat) if lat else float("nan")
        print(f"{m:34} {sum(r['ok'] for r in rs):>3}/{len(rs):<3} {p50:6.2f} {mx:6.2f}")
    for r in runs:
        if not r["ok"] or args.show:
            detail = r.get("error") or "; ".join(r["failures"]) or "ok"
            print(f"\n[{r['model']}] {r['case']}: {detail}\n  -> [{r.get('action')}] {r.get('text', '')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
