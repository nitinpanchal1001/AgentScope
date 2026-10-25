import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

from agentscope_cli.client import AgentScopeClient, ClientError
from agentscope_cli.config import ConfigurationError, RunConfig, load_config

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(EXIT_ERROR)


def _token(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        _fail(f"set {name} to an AgentScope access token")
    return value


def _matches(item: dict[str, Any], value: str) -> bool:
    return value in {
        str(item.get("id", "")),
        str(item.get("slug", "")),
        str(item.get("name", "")),
        str(item.get("version", "")),
    }


def _one(items: list[dict[str, Any]], value: str, resource: str) -> dict[str, Any]:
    matches = [item for item in items if _matches(item, value)]
    if len(matches) != 1:
        raise ClientError(f"Expected one {resource} matching {value!r}; found {len(matches)}")
    return matches[0]


def _resolve_project(client: AgentScopeClient, config: RunConfig) -> dict[str, Any]:
    organizations = client.get("/api/v1/organizations")
    if config.organization:
        organizations = [_one(organizations, config.organization, "organization")]
    projects: list[dict[str, Any]] = []
    for organization in organizations:
        projects.extend(client.get(f"/api/v1/organizations/{organization['id']}/projects"))
    return _one(projects, config.project, "project")


def _resolve_dataset_version(client: AgentScopeClient, project_id: str, config: RunConfig) -> str:
    dataset = _one(client.get(f"/api/v1/projects/{project_id}/datasets"), config.dataset, "dataset")
    versions = dataset["versions"]
    if config.dataset_version == "latest":
        return str(dataset["latest_version"]["id"])
    version = _one(versions, str(config.dataset_version), "dataset version")
    return str(version["id"])


def _resolve_values(
    items: list[dict[str, Any]], values: tuple[str, ...], resource: str
) -> list[str]:
    return [str(_one(items, value, resource)["id"]) for value in values]


def _gate(client: AgentScopeClient, project_id: str, config: RunConfig) -> str | None:
    if config.quality_gate_id:
        return config.quality_gate_id
    if not config.quality_gate_rules:
        return None
    gates = client.get(f"/api/v1/projects/{project_id}/quality-gates")
    matches = [item for item in gates if item["name"] == config.quality_gate_name]
    requested_rules = [rule.__dict__ for rule in config.quality_gate_rules]
    if matches:
        if matches[0]["rules"] != requested_rules:
            raise ClientError(
                f"Quality gate {config.quality_gate_name!r} exists with different rules"
            )
        return str(matches[0]["id"])
    created = client.post(
        f"/api/v1/projects/{project_id}/quality-gates",
        json={"name": config.quality_gate_name, "rules": requested_rules},
    )
    return str(created["id"])


def run_evaluation(config: RunConfig, *, output_json: bool = False) -> int:
    client = AgentScopeClient(config.api_url, _token(config.token_env))
    try:
        project = _resolve_project(client, config)
        project_id = str(project["id"])
        dataset_version_id = _resolve_dataset_version(client, project_id, config)
        environments = client.get(f"/api/v1/projects/{project_id}/environments")
        environment_id = str(_one(environments, config.environment, "environment")["id"])
        evaluator_groups = client.get(f"/api/v1/projects/{project_id}/evaluators")
        evaluator_versions = [
            {**version, "name": group["name"]}
            for group in evaluator_groups
            for version in group["versions"][:1]
        ]
        evaluator_ids = _resolve_values(evaluator_versions, config.evaluators, "evaluator version")
        experiment = client.post(
            f"/api/v1/projects/{project_id}/experiments",
            json={
                "name": config.experiment_name,
                "dataset_version_id": dataset_version_id,
                "environment_id": environment_id,
                "agent": config.agent,
                "evaluator_version_ids": evaluator_ids,
                "max_concurrency": config.max_concurrency,
            },
        )
        experiment_id = str(experiment["id"])
        client.post(f"/api/v1/projects/{project_id}/experiments/{experiment_id}/start")
        experiment = client.wait_for_experiment(
            project_id,
            experiment_id,
            interval=config.poll_interval_seconds,
            timeout=config.timeout_seconds,
        )
        if experiment["status"] != "COMPLETED":
            raise ClientError(
                f"Experiment ended as {experiment['status']}: "
                f"{experiment.get('error_message') or 'no details'}"
            )
        gate_id = _gate(client, project_id, config)
        result = None
        if gate_id:
            result = client.post(
                f"/api/v1/projects/{project_id}/quality-gates/{gate_id}/evaluate",
                json={"candidate_experiment_id": experiment_id},
            )
        payload = {"experiment": experiment, "quality_gate_result": result}
        if output_json:
            print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        else:
            metrics = experiment["metrics"]
            print(f"Experiment {experiment['name']} ({experiment_id}) completed")
            print(
                f"Cases: {experiment['passed_cases']} passed, {experiment['failed_cases']} failed; "
                f"pass rate {float(metrics.get('pass_rate', 0)):.1%}"
            )
            if result:
                print(f"Quality gate: {result['status']}")
                for finding in result["violations"] + result["warnings"]:
                    print(f"- {finding['metric']}: {finding['message']}")
        return EXIT_FAILED if result and result["status"] == "FAILED" else EXIT_PASSED
    finally:
        client.close()


def _direct_client(args: argparse.Namespace) -> AgentScopeClient:
    return AgentScopeClient(args.api_url, _token(args.token_env))


def _print(value: Any, machine: bool) -> None:
    if machine:
        print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentscope")
    parser.add_argument("--version", action="version", version="agentscope 0.7.0")
    commands = parser.add_subparsers(dest="command", required=True)
    auth = commands.add_parser("auth", help="Verify an access token")
    auth.add_argument("--api-url", default="http://localhost:8000")
    auth.add_argument("--token-env", default="AGENTSCOPE_TOKEN")
    auth.add_argument("--json", action="store_true")
    evaluation = commands.add_parser("eval", help="Run evaluations")
    eval_commands = evaluation.add_subparsers(dest="eval_command", required=True)
    run = eval_commands.add_parser("run", help="Run an experiment from agentscope.yaml")
    run.add_argument("--config", type=Path, default=Path("agentscope.yaml"))
    run.add_argument("--json", action="store_true")
    experiment = commands.add_parser("experiment", help="Inspect experiments")
    experiment_commands = experiment.add_subparsers(dest="experiment_command", required=True)
    status = experiment_commands.add_parser("status")
    status.add_argument("--api-url", default="http://localhost:8000")
    status.add_argument("--token-env", default="AGENTSCOPE_TOKEN")
    status.add_argument("--project", required=True)
    status.add_argument("--experiment", required=True)
    status.add_argument("--json", action="store_true")
    gate = commands.add_parser("quality-gate", help="Evaluate a candidate against its baseline")
    gate.add_argument("--api-url", default="http://localhost:8000")
    gate.add_argument("--token-env", default="AGENTSCOPE_TOKEN")
    gate.add_argument("--project", required=True)
    gate.add_argument("--gate", required=True)
    gate.add_argument("--candidate", required=True)
    gate.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "eval":
            return run_evaluation(load_config(args.config), output_json=args.json)
        client = _direct_client(args)
        try:
            if args.command == "auth":
                value = client.get("/api/v1/auth/me")
            elif args.command == "experiment":
                value = client.get(f"/api/v1/projects/{args.project}/experiments/{args.experiment}")
            else:
                value = client.post(
                    f"/api/v1/projects/{args.project}/quality-gates/{args.gate}/evaluate",
                    json={"candidate_experiment_id": args.candidate},
                )
            _print(value, args.json)
            return EXIT_FAILED if value.get("status") == "FAILED" else EXIT_PASSED
        finally:
            client.close()
    except (ClientError, ConfigurationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR


def entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
