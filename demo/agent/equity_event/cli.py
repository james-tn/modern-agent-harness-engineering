"""CLI for the Equity Event Impact Analyst stage demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .runs import ApprovalRequired

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_ROOT.parents[1]
DEFAULT_INPUT = REPO_ROOT / "demo" / "sample-input"
DEFAULT_SKILLS = AGENT_ROOT / "skills"
DEFAULT_LIVE_OUT = AGENT_ROOT / "out" / "live"


async def _live(args: argparse.Namespace) -> int:
    from .live import run_live_episode
    from .live_config import HarnessConfig, profiles

    raw = json.loads(args.config.read_text(encoding="utf-8")) if args.config else profiles()[args.profile]["config"]
    if args.model:
        raw["model"] = args.model
    if args.deployment:
        raw["deployment"] = args.deployment
    if args.memory_scope:
        raw["memory_scope"] = args.memory_scope
    config = HarnessConfig.from_dict(raw)
    root = args.output
    run_id = "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
    out = root / run_id
    memory_dir = args.memory_dir or root / "memory"
    provider = None
    kind = "interactive"
    if args.rehearsal_approval:
        provider = lambda _dashboard, _report: "automated-rehearsal"
        kind = "automated-rehearsal-not-human"
    elif sys.stdin.isatty():
        def provider(dashboard, report):
            print(f"\nReview local dashboard: {dashboard}\nChecks: {report.passed}")
            answer = input("Approve this verified artifact? [y/N] ").strip().lower()
            return args.reviewer if answer in {"yes", "y"} else None
    print(f"Model: {config.model}; deployment: {config.deployment}; output: {out}")
    print("Synthetic data; no external publication. Use 'serve' for the live observability console.")
    try:
        result = await run_live_episode(
            args.input, args.skills, out, config=config, memory_dir=memory_dir,
            approval_provider=provider, approval_kind=kind,
        )
    except ApprovalRequired as error:
        print(f"Awaiting approval: {error}\nEvidence: {out}")
        return 2
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Equity Event Impact Analyst harness.",
        epilog="Legacy A/B commands were retired. Use 'run --model scripted' for offline rehearsal.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--skills", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--output", type=Path, default=DEFAULT_LIVE_OUT)
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("run", help="Live model-driven harness; default profile is progressive/governed.")
    live.add_argument("--profile", choices=("governed", "naive", "scripted"), default="governed")
    live.add_argument("--config", type=Path, help="Validated JSON harness definition; overrides the profile.")
    live.add_argument("--model", choices=("live", "scripted"), help="Explicit backend override; never falls back silently.")
    live.add_argument("--deployment", choices=("gpt-5.6-terra", "gpt-5.4"))
    live.add_argument("--memory-dir", type=Path)
    live.add_argument("--memory-scope")
    live.add_argument("--reviewer", default="local-operator")
    live.add_argument("--rehearsal-approval", action="store_true",
                      help="Automated local validation only; receipt explicitly says NOT a human review.")
    serve = sub.add_parser("serve", help="Local editable harness console and native MAF observability.")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--memory-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return asyncio.run(_live(args))
    if args.command == "serve":
        from .ui import serve
        root = args.output
        serve(args.input, args.skills, root, memory_dir=args.memory_dir or root / "memory", port=args.port)
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
