import time
from typing import Any, cast

import httpx


class ClientError(RuntimeError):
    """An API request failed."""


class AgentScopeClient:
    def __init__(self, api_url: str, token: str, *, timeout: float = 30) -> None:
        self._client = httpx.Client(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise ClientError(f"AgentScope API is unavailable: {error}") from error
        if response.is_error:
            try:
                payload = response.json().get("error", {})
                message = payload.get("message") or response.text
                code = payload.get("code")
            except (ValueError, AttributeError):
                message = response.text
                code = None
            label = f"{code}: " if code else ""
            raise ClientError(f"AgentScope API returned {response.status_code}: {label}{message}")
        return None if response.status_code == 204 else response.json()

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def wait_for_experiment(
        self, project_id: str, experiment_id: str, *, interval: float, timeout: float
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            value = cast(
                dict[str, Any],
                self.get(f"/api/v1/projects/{project_id}/experiments/{experiment_id}"),
            )
            if value["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                return value
            if time.monotonic() >= deadline:
                raise ClientError(f"Experiment {experiment_id} did not finish within {timeout:g}s")
            time.sleep(interval)
