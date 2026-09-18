"""Constrained model-authored arithmetic, not arbitrary agent-authored Python.

Only a trading date and a small arithmetic expression enter the reviewed analysis
template. Python's ``-I`` isolates interpreter configuration; it is NOT an OS
sandbox. Callers must supply policy-admitted, sanitized synthetic input data and
an application-owned output directory.
"""

from __future__ import annotations

import ast
import math
import operator
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from .analysis import ExecutionResult, build_analysis_script, execute_analysis_script

MAX_EXPRESSION_LENGTH = 256
MAX_EXPRESSION_DEPTH = 16
MAX_EXPRESSION_NODES = 64
MAX_LITERAL_MAGNITUDE = 1_000_000

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_EVENT_DATE_STATEMENT = '''
if "event_date_alignment" in CORRECTIONS and event["market_session"] == "after_close":
    event_date = next(row["date"] for row in rows if row["date"] > announced_date)
else:
    event_date = announced_date
'''
_ABNORMAL_RETURN_STATEMENT = '''
abnormal_return = security_return - benchmark_return if use_benchmark else security_return
'''


def _event_returns(payload: dict[str, Any], event_date: str) -> dict[str, float]:
    if not isinstance(event_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", event_date):
        raise ValueError("event_date must be an ISO calendar date (YYYY-MM-DD).")
    try:
        date.fromisoformat(event_date)
    except ValueError as exc:
        raise ValueError("event_date must be a valid ISO calendar date (YYYY-MM-DD).") from exc

    rows = payload["market"]["rows"]
    indices = [i for i, row in enumerate(rows) if row["date"] == event_date]
    if len(indices) != 1 or indices[0] == 0:
        raise ValueError("event_date must identify one available trading row with a prior trading day.")
    idx = indices[0]
    ticker = payload["event"]["ticker"]
    benchmark = payload["market"]["benchmark"]
    try:
        values = {
            "security_return": rows[idx][ticker] / rows[idx - 1][ticker] - 1.0,
            "benchmark_return": rows[idx][benchmark] / rows[idx - 1][benchmark] - 1.0,
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("Selected event prices must produce finite numeric returns.")
    except (ArithmeticError, TypeError) as exc:
        raise ValueError("Selected event prices must produce finite numeric returns.") from exc
    return values


def _validated_expression(expression: str, variables: dict[str, float]) -> str:
    if not isinstance(expression, str) or not 1 <= len(expression) <= MAX_EXPRESSION_LENGTH:
        raise ValueError(f"return_expression must contain 1-{MAX_EXPRESSION_LENGTH} characters.")
    if not re.fullmatch(r"[A-Za-z0-9_+\-*/(). \t]+", expression):
        raise ValueError("return_expression may contain only names, numbers, arithmetic, and parentheses.")
    nesting = 0
    for character in expression:
        if character == "(":
            nesting += 1
            if nesting > MAX_EXPRESSION_DEPTH:
                raise ValueError(f"return_expression nesting exceeds {MAX_EXPRESSION_DEPTH}.")
        elif character == ")":
            nesting -= 1
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError("return_expression must be a valid arithmetic expression.") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_EXPRESSION_NODES:
        raise ValueError(f"return_expression exceeds {MAX_EXPRESSION_NODES} AST nodes.")

    def visit(node: ast.AST, depth: int = 1) -> int | float:
        if depth > MAX_EXPRESSION_DEPTH:
            raise ValueError(f"return_expression AST depth exceeds {MAX_EXPRESSION_DEPTH}.")
        if isinstance(node, ast.Constant):
            value = node.value
            if (
                type(value) not in (int, float)
                or abs(value) > MAX_LITERAL_MAGNITUDE
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"return_expression constants must be finite numbers with magnitude <= {MAX_LITERAL_MAGNITUDE}."
                )
        elif isinstance(node, ast.Name) and node.id in variables and isinstance(node.ctx, ast.Load):
            value = variables[node.id]
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            value = _BINARY_OPERATORS[type(node.op)](visit(node.left, depth + 1), visit(node.right, depth + 1))
        elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            value = _UNARY_OPERATORS[type(node.op)](visit(node.operand, depth + 1))
        else:
            raise ValueError(
                "return_expression permits only security_return, benchmark_return, numeric constants, and + - * /."
            )
        if not math.isfinite(value):
            raise ValueError("return_expression arithmetic must remain finite.")
        return value

    try:
        visit(tree.body)
    except ArithmeticError as exc:
        raise ValueError("return_expression arithmetic is undefined or non-finite.") from exc
    return ast.unparse(tree.body)


def _replace_once(script: str, target: str, replacement: str, label: str) -> str:
    if script.count(target) != 1:
        raise ValueError(f"Reviewed template must contain exactly one {label} statement; refusing execution.")
    return script.replace(target, replacement, 1)


def _output_text(value: str | bytes | None) -> str:
    return (value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or "").strip()


def execute_live_analysis(
    payload: dict[str, Any], event_date: str, return_expression: str, out_dir: Path, *, timeout_seconds: int = 15
) -> ExecutionResult:
    """Execute only constrained model-authored arithmetic in the reviewed template.

    The expression permits two names (``security_return``, ``benchmark_return``),
    finite numeric literals of magnitude at most 1,000,000, unary/binary ``+ -``,
    ``* /``, and parentheses. Limits are 256 characters, 16 levels, and 64 AST
    nodes. A small allowlisted AST interpreter rejects undefined/nonfinite
    arithmetic before the same arithmetic is executed by real Python.
    There is no ``eval`` and no arbitrary model-supplied program or OS sandbox.

    Invalid inputs or template drift raise ``ValueError``. Dates must exist in
    the supplied trading rows and have a prior row; a valid but incorrect date
    or formula is NOT repaired. The independent verifier decides correctness.
    Every attempt clears old artifacts. Subprocess failures return evidence,
    retain generated source, and remove partial JSON/HTML. Timeout return codes
    are 124; process-start/IO exceptions use -1. ``timeout_seconds`` must be an
    integer from 1 through 30 (not a boolean), defaults to 15, and is forwarded
    to the executor. Invalid timeouts raise ``ValueError`` before execution.
    """
    out_dir = Path(out_dir).resolve()
    script_path = out_dir / "generated_analysis.py"
    analysis_path = out_dir / "analysis.json"
    dashboard_path = out_dir / "dashboard.html"
    for artifact in (script_path, analysis_path, dashboard_path):
        artifact.unlink(missing_ok=True)

    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
        raise ValueError("timeout_seconds must be an integer from 1 through 30 (not a boolean).")

    variables = _event_returns(payload, event_date)
    expression = _validated_expression(return_expression, variables)
    script = build_analysis_script(payload, mode="governed", corrections=[])
    script = _replace_once(script, _EVENT_DATE_STATEMENT, f"\nevent_date = {event_date!r}\n", "event-date")
    script = _replace_once(
        script, _ABNORMAL_RETURN_STATEMENT, f"\nabnormal_return = {expression}\n", "abnormal-return"
    )
    try:
        execution = execute_analysis_script(script, out_dir, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        detail = f"Python subprocess timed out after {exc.timeout} seconds."
        execution = ExecutionResult(
            success=False,
            return_code=124,
            stdout=_output_text(exc.stdout),
            stderr="\n".join(part for part in (_output_text(exc.stderr), detail) if part),
            script_path=script_path,
            analysis_path=analysis_path,
            dashboard_path=dashboard_path,
        )
    except OSError as exc:
        execution = ExecutionResult(
            success=False,
            return_code=-1,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
            script_path=script_path,
            analysis_path=analysis_path,
            dashboard_path=dashboard_path,
        )
    if not execution.success:
        for artifact in (analysis_path, dashboard_path):
            artifact.unlink(missing_ok=True)
        if not execution.stderr:
            execution.stderr = "Analysis execution failed or did not produce both required nonempty artifacts."
    return execution
