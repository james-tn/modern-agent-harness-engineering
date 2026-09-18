"""Offline coverage of constrained model-authored arithmetic, not arbitrary Python."""

from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
from pathlib import Path

import pytest

from equity_event import live_analysis
from equity_event.analysis import build_analysis_script, execute_analysis_script
from equity_event.domain import load_episode
from equity_event.harness.policy import admit
from equity_event.harness.verifier import BASE_VERSION, verify
from equity_event.live_analysis import execute_live_analysis

SAMPLE_INPUT = Path(__file__).resolve().parents[3] / "demo" / "sample-input"
EVENT_DATE = "2026-08-06"
FORMULA = "security_return - benchmark_return"
ARTIFACTS = ("generated_analysis.py", "analysis.json", "dashboard.html")


@pytest.fixture(scope="module")
def episode():
    return load_episode(SAMPLE_INPUT)


@pytest.fixture
def payload(episode):
    policy = admit(episode)
    return copy.deepcopy(episode.model_payload(governed=True, admitted_claim_ids=set(policy.admitted_claim_ids)))


@pytest.fixture
def execution(payload, tmp_path):
    result = execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path)
    assert result.success, result.stderr
    return result


def test_correct_result_is_executed_and_independently_verified(episode, execution):
    report = verify(episode, execution, admit(episode))
    assert report.passed, report.to_dict()
    assert len(report.checks) == 9
    assert len(verify(episode, execution, admit(episode), version=BASE_VERSION).checks) == 8
    analysis = json.loads(execution.analysis_path.read_text(encoding="utf-8"))
    assert analysis["event_date"] == EVENT_DATE
    assert analysis["returns"]["abnormal"] == pytest.approx((110 / 101 - 1) - (103 / 100 - 1))
    assert analysis["sections"]["market_reaction"]["abnormal_return"] == analysis["returns"]["abnormal"]
    assert analysis["sections"]["portfolio_exposure"] == {"exposure_band": "medium (2%-5%)"}
    assert analysis["data_classification"] == "synthetic-illustrative"
    assert execution.return_code == 0
    assert execution.stderr == ""
    assert json.loads(execution.stdout) == {
        "analysis": str(execution.analysis_path),
        "dashboard": str(execution.dashboard_path),
    }
    assert sorted(path.name for path in execution.script_path.parent.iterdir()) == sorted(ARTIFACTS)
    source = execution.script_path.read_text(encoding="utf-8")
    assert f"event_date = {EVENT_DATE!r}" in source
    assert f"abnormal_return = {FORMULA}" in source
    targets = [
        target.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in {"event_date", "abnormal_return"}
    ]
    assert sorted(targets) == ["abnormal_return", "event_date"]


@pytest.mark.parametrize(
    "mode,corrections",
    [("baseline", []), ("governed", []), ("governed", ["event_date_alignment"])],
)
def test_verifier_preserves_existing_template_behavior(episode, tmp_path, mode, corrections):
    policy = admit(episode)
    payload = episode.model_payload(governed=mode == "governed", admitted_claim_ids=set(policy.admitted_claim_ids))
    result = execute_analysis_script(build_analysis_script(payload, mode=mode, corrections=corrections), tmp_path)
    report = verify(episode, result, policy)
    assert report.checks[0].passed
    assert len(report.checks) == 9
    if mode == "baseline":
        assert {
            "approved_method", "claim_provenance", "restricted_data_excluded",
            "causal_claim_guard", "event_date_alignment",
        } <= {check.code for check in report.failures}
    elif not corrections:
        assert {check.code for check in report.failures} == {"event_date_alignment"}
    else:
        assert report.passed


@pytest.mark.parametrize(
    "event_date,expression,failure",
    [
        ("2026-08-05", FORMULA, "event_date_alignment"),
        ("2026-08-07", FORMULA, "event_date_alignment"),
        (EVENT_DATE, "security_return + benchmark_return", "independent_recalculation"),
        (EVENT_DATE, "security_return", "independent_recalculation"),
        (EVENT_DATE, "0", "independent_recalculation"),
    ],
)
def test_wrong_choices_are_observable_not_repaired(payload, episode, tmp_path, event_date, expression, failure):
    result = execute_live_analysis(payload, event_date, expression, tmp_path)
    assert result.success, result.stderr
    report = verify(episode, result, admit(episode))
    assert {check.code for check in report.failures} == {failure}
    analysis = json.loads(result.analysis_path.read_text(encoding="utf-8"))
    assert analysis["event_date"] == event_date
    source = ast.parse(result.script_path.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in source.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "abnormal_return" for target in node.targets
        )
    )
    assert ast.dump(assignment.value) == ast.dump(ast.parse(expression, mode="eval").body)


@pytest.mark.parametrize(
    "expression",
    [
        " (security_return - benchmark_return) ",
        "+security_return + -benchmark_return",
        "(security_return - benchmark_return) * 2 / 2 + 0",
        "0.5 * (2 * security_return - 2 * benchmark_return)",
        "security_return - benchmark_return + 1e-6 - 0.000001",
    ],
)
def test_allowed_arithmetic(payload, episode, tmp_path, expression):
    result = execute_live_analysis(payload, EVENT_DATE, expression, tmp_path)
    assert result.success, result.stderr
    assert verify(episode, result, admit(episode)).passed


@pytest.mark.parametrize(
    "expression",
    [
        None, 42, True, "", "   ",
        "__import__('os').system('echo unsafe')",
        "security_return.__class__",
        "security_return.real",
        "abs(security_return)",
        "float('inf')",
        "(lambda: 1)()",
        "[security_return][0]",
        "(security_return, benchmark_return)",
        "{security_return: benchmark_return}",
        "[x for x in (1,)]",
        "(security_return := 0)",
        "security_return; print(1)",
        "security_return\nprint(1)",
        "security_return # ignored",
        "security_return\x00",
        "security_return\\\n+benchmark_return",
        "ｓｅｃｕｒｉｔｙ_return",
        "'security_return'",
        "unknown_return",
        "DATA",
        "nan", "inf", "math.inf", "True", "None", "1j",
        "security_return ** 2",
        "security_return // 2",
        "security_return % 2",
        "1 << 2",
        "security_return @ benchmark_return",
        "security_return if 1 else benchmark_return",
        "security_return and benchmark_return",
        "1e309", "-1e309", "1000001", "-1000001",
        "security_return / 0",
        "security_return / (benchmark_return - benchmark_return)",
        "(1 / 1e-308) * 1000000",
        "1 / 1e-320",
        "0 * (1 / 0)",
    ],
)
def test_invalid_or_nonfinite_expressions_fail_before_execution(payload, tmp_path, monkeypatch, expression):
    def must_not_execute(*args, **kwargs):
        pytest.fail("An invalid expression reached Python execution.")

    monkeypatch.setattr(live_analysis, "execute_analysis_script", must_not_execute)
    for name in ARTIFACTS:
        (tmp_path / name).write_text("stale", encoding="utf-8")
    with pytest.raises(ValueError, match="return_expression"):
        execute_live_analysis(payload, EVENT_DATE, expression, tmp_path)
    assert not any((tmp_path / name).exists() for name in ARTIFACTS)


def test_expression_complexity_is_bounded(payload, tmp_path):
    balanced = "1"
    for _ in range(5):
        balanced = f"({balanced}+{balanced})"
    expressions = [
        "1+" * 128 + "1",
        "-" * 17 + "1",
        "(" * 17 + "1" + ")" * 17,
        balanced,
    ]
    for expression in expressions:
        with pytest.raises(ValueError, match="return_expression"):
            execute_live_analysis(payload, EVENT_DATE, expression, tmp_path)
    assert not any((tmp_path / name).exists() for name in ARTIFACTS)


@pytest.mark.parametrize(
    "event_date",
    [
        None, 20260806, "", "20260806", "2026-8-6", "2026-02-30", "0000-01-01",
        "2026-08-06T00:00:00", " 2026-08-06", "2026-08-06\n",
        "2026-08-08", "2026-08-03", "2026-08-06'; print(1); '",
    ],
)
def test_invalid_dates_are_explicit_errors(payload, tmp_path, event_date):
    with pytest.raises(ValueError, match="event_date"):
        execute_live_analysis(payload, event_date, FORMULA, tmp_path)
    assert not any((tmp_path / name).exists() for name in ARTIFACTS)


@pytest.mark.parametrize("target", [live_analysis._EVENT_DATE_STATEMENT, live_analysis._ABNORMAL_RETURN_STATEMENT])
@pytest.mark.parametrize("change", ["missing", "duplicate"])
def test_template_replacements_require_exactly_one_target(payload, tmp_path, monkeypatch, target, change):
    original = live_analysis.build_analysis_script

    def drifted_template(*args, **kwargs):
        source = original(*args, **kwargs)
        return source.replace(target, "") if change == "missing" else source + target

    monkeypatch.setattr(live_analysis, "build_analysis_script", drifted_template)
    with pytest.raises(ValueError, match="exactly one"):
        execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path)
    assert not any((tmp_path / name).exists() for name in ARTIFACTS)


def test_relative_output_directory_and_existing_artifacts(payload, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output = Path("nested") / "attempt"
    output.mkdir(parents=True)
    for name in ARTIFACTS:
        (output / name).write_text("stale", encoding="utf-8")
    (output / "unrelated.txt").write_text("keep", encoding="utf-8")
    result = execute_live_analysis(payload, EVENT_DATE, FORMULA, output)
    assert result.success, result.stderr
    assert result.script_path.is_absolute()
    assert json.loads(result.analysis_path.read_text(encoding="utf-8"))["event_date"] == EVENT_DATE
    assert (output / "unrelated.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("timeout_seconds", [None, 1, 7, 30])
def test_timeout_is_forwarded_to_real_subprocess(payload, episode, tmp_path, monkeypatch, timeout_seconds):
    original_run = subprocess.run
    observed_timeouts = []

    def record_timeout(command, **kwargs):
        observed_timeouts.append(kwargs["timeout"])
        return original_run(command, **kwargs)

    monkeypatch.setattr("equity_event.analysis.subprocess.run", record_timeout)
    options = {} if timeout_seconds is None else {"timeout_seconds": timeout_seconds}
    result = execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path, **options)
    assert observed_timeouts == [15 if timeout_seconds is None else timeout_seconds]
    assert result.success, result.stderr
    assert verify(episode, result, admit(episode)).passed


@pytest.mark.parametrize(
    "timeout_seconds",
    [None, True, False, 0, -1, 31, 10 ** 100, 1.0, 15.5, float("nan"), float("inf"), "15", [], {}],
)
def test_invalid_timeout_fails_before_execution(payload, tmp_path, monkeypatch, timeout_seconds):
    def must_not_execute(*args, **kwargs):
        pytest.fail("An invalid timeout reached Python execution.")

    monkeypatch.setattr(live_analysis, "execute_analysis_script", must_not_execute)
    for name in ARTIFACTS:
        (tmp_path / name).write_text("stale", encoding="utf-8")
    with pytest.raises(ValueError, match="timeout_seconds must be an integer from 1 through 30"):
        execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path, timeout_seconds=timeout_seconds)
    assert not any((tmp_path / name).exists() for name in ARTIFACTS)


def test_timeout_is_keyword_only(payload, tmp_path):
    with pytest.raises(TypeError, match="positional"):
        execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path, 10)
    assert not any((tmp_path / name).exists() for name in ARTIFACTS)


@pytest.mark.parametrize("timeout_seconds", [1, 15, 30])
@pytest.mark.parametrize("failure", ["timeout", "launch", "nonzero", "incomplete"])
def test_subprocess_failures_preserve_source_and_remove_outputs(
    payload, episode, tmp_path, monkeypatch, failure, timeout_seconds
):
    for name in ARTIFACTS:
        (tmp_path / name).write_text("stale", encoding="utf-8")
    monkeypatch.setenv("LIVE_TEST_SECRET", "must-not-reach-child")

    def fail_process(command, **kwargs):
        assert command[1] == "-I"
        assert kwargs["timeout"] == timeout_seconds
        assert "LIVE_TEST_SECRET" not in kwargs["env"]
        assert kwargs["cwd"] == tmp_path
        assert Path(command[2]).read_text(encoding="utf-8") != "stale"
        assert not (tmp_path / "analysis.json").exists()
        assert not (tmp_path / "dashboard.html").exists()
        (tmp_path / "analysis.json").write_text('{"partial": true}', encoding="utf-8")
        if failure != "incomplete":
            (tmp_path / "dashboard.html").write_text("<p>partial</p>", encoding="utf-8")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                command, timeout_seconds, output=b"partial stdout\xff\n", stderr=b"partial stderr\n"
            )
        if failure == "launch":
            raise OSError("seeded process launch failure")
        return subprocess.CompletedProcess(
            command, 9 if failure == "nonzero" else 0, "partial stdout\n",
            "seeded execution failure\n" if failure == "nonzero" else "",
        )

    monkeypatch.setattr("equity_event.analysis.subprocess.run", fail_process)
    result = execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path, timeout_seconds=timeout_seconds)
    assert not result.success
    assert result.script_path.is_file()
    ast.parse(result.script_path.read_text(encoding="utf-8"))
    assert not result.analysis_path.exists()
    assert not result.dashboard_path.exists()
    assert result.stderr
    if failure == "timeout":
        assert result.return_code == 124
        assert result.stdout == "partial stdout\ufffd"
        assert "partial stderr" in result.stderr
        assert f"timed out after {timeout_seconds} seconds" in result.stderr
    elif failure == "launch":
        assert result.return_code == -1
        assert "seeded process launch failure" in result.stderr
    elif failure == "nonzero":
        assert result.return_code == 9
        assert result.stdout == "partial stdout"
        assert result.stderr == "seeded execution failure"
    else:
        assert result.return_code == 0
        assert "nonempty artifacts" in result.stderr
    report = verify(episode, result, admit(episode))
    assert not report.passed
    assert [check.code for check in report.failures] == ["script_execution"]


def test_real_template_execution_failure_returns_evidence(payload, tmp_path):
    del payload["position"]["exposure_band"]
    result = execute_live_analysis(payload, EVENT_DATE, FORMULA, tmp_path)
    assert not result.success
    assert result.return_code != 0
    assert "KeyError" in result.stderr
    assert result.script_path.is_file()
    assert not result.analysis_path.exists()
    assert not result.dashboard_path.exists()


@pytest.mark.parametrize("contents", ["", "{", "[]", "null", "12", '"text"', "{}", '{"value": NaN}'])
def test_malformed_analysis_json_is_a_failed_check(episode, execution, contents):
    execution.analysis_path.write_text(contents, encoding="utf-8")
    report = verify(episode, execution, admit(episode))
    assert not report.passed
    assert [check.code for check in report.failures] == ["script_execution"]
    assert "Invalid analysis artifacts" in report.failures[0].detail


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_date", []),
        ("returns", None), ("returns", {}),
        ("returns.security", "0.1"), ("returns.benchmark", True),
        ("returns.abnormal", float("nan")), ("returns.abnormal", float("inf")),
        ("returns.abnormal", 10 ** 400),
        ("method", []), ("method", {}),
        ("method.prices_adjusted", "true"), ("method.benchmark_adjusted", 1),
        ("method.benchmark", {}),
        ("evidence_ids", None), ("evidence_ids", "src-market-snapshot"),
        ("evidence_ids", [{}]), ("evidence_ids", [1, "source"]),
        ("sections", []), ("sections", None),
        ("series", None), ("series", []), ("series", [None]),
        ("series", [{"date": "2026-08-03", "security_index": True, "benchmark_index": 100}]),
    ],
)
def test_invalid_analysis_keys_and_types_fail_closed(episode, execution, field, value):
    analysis = json.loads(execution.analysis_path.read_text(encoding="utf-8"))
    parent = analysis
    keys = field.split(".")
    for key in keys[:-1]:
        parent = parent[key]
    parent[keys[-1]] = value
    execution.analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    report = verify(episode, execution, admit(episode))
    assert not report.passed
    assert [check.code for check in report.failures] == ["script_execution"]


@pytest.mark.parametrize("chart", ["not json", "{", "null", "{}", "[]", "[NaN]", "[Infinity]"])
def test_invalid_chart_json_is_a_failed_check(episode, execution, chart):
    dashboard = execution.dashboard_path.read_text(encoding="utf-8")
    dashboard = re.sub(
        r'(<script type="application/json" id="chart-data">).*?(</script>)',
        lambda match: match.group(1) + chart + match.group(2),
        dashboard,
        flags=re.DOTALL,
    )
    execution.dashboard_path.write_text(dashboard, encoding="utf-8")
    report = verify(episode, execution, admit(episode))
    assert not report.passed
    assert {check.code for check in report.failures} == {"chart_data_integrity"}
    assert len(report.checks) == 9


def test_missing_chart_json_is_a_failed_check(episode, execution):
    dashboard = execution.dashboard_path.read_text(encoding="utf-8").replace('id="chart-data"', 'id="missing"')
    execution.dashboard_path.write_text(dashboard, encoding="utf-8")
    assert {check.code for check in verify(episode, execution, admit(episode)).failures} == {"chart_data_integrity"}


@pytest.mark.parametrize("artifact", ["analysis_path", "dashboard_path"])
def test_invalid_artifact_encoding_is_a_failed_check(episode, execution, artifact):
    getattr(execution, artifact).write_bytes(b"\xff")
    report = verify(episode, execution, admit(episode))
    assert [check.code for check in report.failures] == ["script_execution"]
