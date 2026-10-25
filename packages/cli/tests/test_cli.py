import json
from pathlib import Path

import pytest

from agentscope_cli import main
from agentscope_cli.client import AgentScopeClient
from agentscope_cli.config import ConfigurationError, load_config


def test_loads_documented_quality_gate_shorthand(tmp_path: Path) -> None:
    path = tmp_path / "agentscope.yaml"
    path.write_text(
        """
project: customer-support
dataset: golden-v3
environment: development
evaluators: [correctness, hallucination]
agent:
  endpoint: https://agent.example.com/invoke
quality_gate:
  name: Release gate
  correctness:
    max_regression: 0.03
  hallucination:
    max_increase: 0.02
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.project == "customer-support"
    assert [rule.metric for rule in config.quality_gate_rules] == [
        "average_correctness",
        "hallucination_rate",
    ]
    assert config.quality_gate_rules[0].severity == "FAIL"
    assert config.quality_gate_rules[1].comparison == "absolute"


def test_invalid_configuration_uses_execution_error_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "agentscope.yaml"
    path.write_text("project: support\n", encoding="utf-8")
    assert main.main(["eval", "run", "--config", str(path)]) == 2
    assert "agent must be a mapping" in capsys.readouterr().err


def test_quality_gate_exit_codes_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AGENTSCOPE_TOKEN", "test-token")
    monkeypatch.setattr(AgentScopeClient, "close", lambda self: None)
    monkeypatch.setattr(
        AgentScopeClient,
        "post",
        lambda self, path, **kwargs: {
            "id": "result-1",
            "status": "FAILED",
            "violations": [{"metric": "pass_rate"}],
        },
    )
    exit_code = main.main(
        [
            "quality-gate",
            "--project",
            "project-1",
            "--gate",
            "gate-1",
            "--candidate",
            "experiment-1",
            "--json",
        ]
    )
    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED"


def test_missing_token_is_execution_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main.main(["auth", "--token-env", "MISSING_TEST_TOKEN"])
    assert error.value.code == 2
    assert "MISSING_TEST_TOKEN" in capsys.readouterr().err


def test_negative_threshold_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "agentscope.yaml"
    path.write_text(
        """
project: support
dataset: golden
evaluators: [exact]
agent: {endpoint: https://agent.example.com/invoke}
quality_gate:
  pass_rate: {max_regression: -0.1}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="cannot be negative"):
        load_config(path)
