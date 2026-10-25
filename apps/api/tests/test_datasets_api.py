import json

from conftest import register_user
from httpx import AsyncClient


async def _workspace(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    token, _ = await register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": f"Dataset {email}"}, headers=headers
    )
    project = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/projects",
        json={"name": "Golden Cases"},
        headers=headers,
    )
    return headers, project.json()["id"]


async def test_dataset_versions_are_immutable_and_tenant_scoped(client: AsyncClient) -> None:
    headers, project_id = await _workspace(client, "datasets@example.com")
    first_case = {
        "input": {"message": "Where is order A-42?"},
        "expected_output": {"status": "shipped"},
        "expected_tools": ["lookup_order"],
        "context": {"order_id": "A-42"},
        "metadata": {"priority": "golden"},
    }
    created = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=headers,
        json={
            "name": "Support Golden Dataset",
            "description": "Stable customer-support regression cases",
            "metadata": {"source": "manual"},
            "items": [first_case],
        },
    )
    assert created.status_code == 201, created.text
    dataset_id = created.json()["id"]
    assert created.json()["latest_version"]["version"] == 1
    assert created.json()["latest_version"]["item_count"] == 1
    assert len(created.json()["latest_version"]["content_hash"]) == 64

    duplicate_name = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"name": "Support Golden Dataset", "items": [{"input": "another"}]},
    )
    assert duplicate_name.status_code == 409

    duplicate = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions",
        headers=headers,
        json={"metadata": {"source": "manual"}, "items": [first_case]},
    )
    assert duplicate.status_code == 409

    appended = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/items",
        headers=headers,
        json={
            "case": {
                "input": "Please cancel order B-10",
                "expected_output": "Order B-10 was cancelled",
                "expected_tools": ["cancel_order"],
            },
            "metadata": {"change_note": "Add cancellation coverage"},
        },
    )
    assert appended.status_code == 201, appended.text
    assert appended.json()["version"] == 2
    assert appended.json()["item_count"] == 2

    version_one = await client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/1",
        headers=headers,
    )
    version_two = await client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/2",
        params={"page": 1, "page_size": 1},
        headers=headers,
    )
    assert version_one.json()["version"]["item_count"] == 1
    assert version_one.json()["items"][0]["input"] == first_case["input"]
    assert version_two.json()["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total_items": 2,
        "total_pages": 2,
        "has_next": True,
        "has_previous": False,
    }

    foreign_headers, foreign_project_id = await _workspace(client, "foreign-datasets@example.com")
    hidden = await client.get(
        f"/api/v1/projects/{foreign_project_id}/datasets/{dataset_id}",
        headers=foreign_headers,
    )
    assert hidden.status_code == 404


async def test_jsonl_and_csv_import_validate_before_commit(client: AsyncClient) -> None:
    headers, project_id = await _workspace(client, "dataset-import@example.com")
    created = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"name": "Imported Cases", "items": [{"input": "seed"}]},
    )
    dataset_id = created.json()["id"]
    jsonl = "\n".join(
        json.dumps(item)
        for item in [
            {"input": "Question one", "expected_output": "Answer one"},
            {
                "input": {"question": "Question two"},
                "expected_tools": ["search_knowledge"],
                "metadata": {"category": "knowledge"},
            },
        ]
    )
    imported = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/import",
        headers=headers,
        data={"format": "jsonl", "metadata": '{"source":"fixture"}'},
        files={"file": ("cases.jsonl", jsonl, "application/x-ndjson")},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["version"] == 2
    assert imported.json()["item_count"] == 2

    invalid = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/import",
        headers=headers,
        data={"format": "jsonl"},
        files={"file": ("broken.jsonl", '{"input":"ok"}\n{"expected_tools":"bad"}')},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_DATASET_CASE"
    assert invalid.json()["error"]["details"]["row"] == 2

    after_invalid = await client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}", headers=headers
    )
    assert [version["version"] for version in after_invalid.json()["versions"]] == [2, 1]

    csv_content = (
        "input,expected_output,expected_tools,context,metadata\n"
        'Hello,Hi,"[""answer""]",,"{""language"":""en""}"\n'
    )
    csv_import = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/import",
        headers=headers,
        data={"format": "csv"},
        files={"file": ("cases.csv", csv_content, "text/csv")},
    )
    assert csv_import.status_code == 201, csv_import.text
    assert csv_import.json()["version"] == 3
