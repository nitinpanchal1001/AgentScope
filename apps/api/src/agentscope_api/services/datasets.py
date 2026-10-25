import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.config import Settings
from agentscope_api.core.exceptions import AppError, ConflictError, NotFoundError
from agentscope_api.models import (
    Dataset,
    DatasetItem,
    DatasetVersion,
    Membership,
    Project,
    User,
)
from agentscope_api.repositories.datasets import DatasetRepository
from agentscope_api.schemas.datasets import (
    DatasetAppendCase,
    DatasetCase,
    DatasetCreate,
    DatasetImportFormat,
    DatasetVersionCreate,
)
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission


def _canonical_case(case: DatasetCase) -> dict[str, Any]:
    return case.model_dump(mode="json")


def dataset_content_hash(items: list[DatasetCase], metadata: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"items": [_canonical_case(item) for item in items], "metadata": metadata},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validation_error(row: int, error: ValidationError) -> AppError:
    violations = [
        {
            "location": [str(part) for part in issue["loc"]],
            "message": issue["msg"],
            "type": issue["type"],
        }
        for issue in error.errors()
    ]
    return AppError(
        "INVALID_DATASET_CASE",
        f"Dataset case {row} is invalid",
        status_code=422,
        details={"row": row, "violations": violations},
    )


def _validate_cases(raw_items: list[Any], maximum: int) -> list[DatasetCase]:
    if not raw_items:
        raise AppError(
            "EMPTY_DATASET",
            "A dataset version must contain at least one case",
            status_code=422,
        )
    if len(raw_items) > maximum:
        raise AppError(
            "DATASET_TOO_LARGE",
            f"A dataset version may contain at most {maximum} cases",
            status_code=413,
            details={"maximum": maximum, "received": len(raw_items)},
        )
    cases: list[DatasetCase] = []
    for row, item in enumerate(raw_items, start=1):
        try:
            cases.append(DatasetCase.model_validate(item))
        except ValidationError as error:
            raise _validation_error(row, error) from error
    return cases


def _parse_json(content: str) -> list[Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AppError(
            "INVALID_DATASET_IMPORT",
            f"Invalid JSON at line {error.lineno}, column {error.colno}",
            status_code=422,
            details={"line": error.lineno, "column": error.colno},
        ) from error
    if isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list):
        raise AppError(
            "INVALID_DATASET_IMPORT",
            "JSON import must be an array or an object containing an items array",
            status_code=422,
        )
    return payload


def _parse_jsonl(content: str) -> list[Any]:
    items: list[Any] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise AppError(
                "INVALID_DATASET_IMPORT",
                f"Invalid JSONL record on line {line_number}",
                status_code=422,
                details={"line": line_number, "column": error.colno},
            ) from error
        items.append(value)
    return items


def _cell_json(value: str | None, *, field: str, row: int, fallback_text: bool) -> Any:
    if value is None or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        if fallback_text:
            return value
        raise AppError(
            "INVALID_DATASET_IMPORT",
            f"CSV row {row} field {field} must contain valid JSON",
            status_code=422,
            details={"row": row, "field": field},
        ) from error


def _parse_csv(content: str) -> list[Any]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or "input" not in reader.fieldnames:
        raise AppError(
            "INVALID_DATASET_IMPORT",
            "CSV import requires an input header",
            status_code=422,
        )
    items: list[dict[str, Any]] = []
    for row_number, row in enumerate(reader, start=2):
        expected_tools = _cell_json(
            row.get("expected_tools"), field="expected_tools", row=row_number, fallback_text=False
        )
        metadata = _cell_json(
            row.get("metadata"), field="metadata", row=row_number, fallback_text=False
        )
        items.append(
            {
                "input": _cell_json(
                    row.get("input"), field="input", row=row_number, fallback_text=True
                ),
                "expected_output": _cell_json(
                    row.get("expected_output"),
                    field="expected_output",
                    row=row_number,
                    fallback_text=True,
                ),
                "expected_tools": expected_tools or [],
                "context": _cell_json(
                    row.get("context"), field="context", row=row_number, fallback_text=True
                ),
                "metadata": metadata or {},
            }
        )
    return items


def parse_dataset_import(
    content: bytes,
    import_format: DatasetImportFormat,
    *,
    max_bytes: int,
    max_items: int,
) -> list[DatasetCase]:
    if len(content) > max_bytes:
        raise AppError(
            "DATASET_IMPORT_TOO_LARGE",
            "Dataset import exceeds the configured byte limit",
            status_code=413,
            details={"maximum_bytes": max_bytes},
        )
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AppError(
            "INVALID_DATASET_IMPORT",
            "Dataset imports must use UTF-8 encoding",
            status_code=422,
        ) from error
    if import_format == "json":
        raw_items = _parse_json(decoded)
    elif import_format == "jsonl":
        raw_items = _parse_jsonl(decoded)
    else:
        raw_items = _parse_csv(decoded)
    return _validate_cases(raw_items, max_items)


class DatasetService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = DatasetRepository(session)

    async def create_dataset(
        self,
        project: Project,
        membership: Membership,
        request: DatasetCreate,
        user: User,
    ) -> tuple[Dataset, DatasetVersion]:
        require_permission(membership.role, Permission.DATASET_MANAGE)
        self._check_size(request.items)
        dataset = Dataset(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            name=request.name,
            description=request.description,
            created_by=user.id,
        )
        try:
            self.repository.add(dataset)
            await self.session.flush()
            version = await self._insert_version(
                dataset, 1, request.items, request.metadata, user.id
            )
            record_audit(
                self.session,
                organization_id=project.organization_id,
                actor_id=user.id,
                action="dataset.created",
                resource_type="dataset",
                resource_id=dataset.id,
                metadata={"version": 1, "item_count": len(request.items)},
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("A dataset with this name already exists") from error
        return dataset, version

    async def create_version(
        self,
        project: Project,
        membership: Membership,
        dataset_id: UUID,
        request: DatasetVersionCreate,
        user: User,
    ) -> DatasetVersion:
        require_permission(membership.role, Permission.DATASET_MANAGE)
        self._check_size(request.items)
        dataset = await self.repository.lock_dataset(dataset_id, project.id)
        if dataset is None:
            raise NotFoundError("Dataset")
        content_hash = dataset_content_hash(request.items, request.metadata)
        if await self.repository.find_content_hash(dataset.id, content_hash) is not None:
            raise ConflictError("An identical immutable dataset version already exists")
        version_number = await self.repository.next_version(dataset.id)
        version = await self._insert_version(
            dataset, version_number, request.items, request.metadata, user.id
        )
        dataset.updated_at = datetime.now(UTC)
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="dataset.version_created",
            resource_type="dataset_version",
            resource_id=version.id,
            metadata={"dataset_id": str(dataset.id), "version": version_number},
        )
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("A conflicting dataset version was created concurrently") from error
        return version

    async def append_case(
        self,
        project: Project,
        membership: Membership,
        dataset_id: UUID,
        request: DatasetAppendCase,
        user: User,
    ) -> DatasetVersion:
        require_permission(membership.role, Permission.DATASET_MANAGE)
        dataset = await self.repository.lock_dataset(dataset_id, project.id)
        if dataset is None:
            raise NotFoundError("Dataset")
        versions = await self.repository.list_versions(dataset.id)
        if not versions:
            raise NotFoundError("Dataset version")
        latest = versions[0]
        stored_items = await self.repository.list_items(latest.id)
        items = [
            DatasetCase(
                input=item.input,
                expected_output=item.expected_output,
                expected_tools=item.expected_tools,
                context=item.context,
                metadata=item.item_metadata,
            )
            for item in stored_items
        ]
        items.append(request.case)
        metadata = {
            **request.metadata,
            "operation": "append_case",
            "parent_version": latest.version,
        }
        return await self.create_version(
            project,
            membership,
            dataset.id,
            DatasetVersionCreate(items=items, metadata=metadata),
            user,
        )

    async def create_import_version(
        self,
        project: Project,
        membership: Membership,
        dataset_id: UUID,
        *,
        content: bytes,
        import_format: DatasetImportFormat,
        metadata: dict[str, Any],
        user: User,
    ) -> DatasetVersion:
        items = parse_dataset_import(
            content,
            import_format,
            max_bytes=self.settings.dataset_max_import_bytes,
            max_items=self.settings.dataset_max_items_per_version,
        )
        return await self.create_version(
            project,
            membership,
            dataset_id,
            DatasetVersionCreate(items=items, metadata=metadata),
            user,
        )

    def _check_size(self, items: list[DatasetCase]) -> None:
        if len(items) > self.settings.dataset_max_items_per_version:
            raise AppError(
                "DATASET_TOO_LARGE",
                "Dataset version contains too many cases",
                status_code=413,
                details={"maximum": self.settings.dataset_max_items_per_version},
            )

    async def _insert_version(
        self,
        dataset: Dataset,
        version_number: int,
        items: list[DatasetCase],
        metadata: dict[str, Any],
        user_id: UUID,
    ) -> DatasetVersion:
        version = DatasetVersion(
            id=uuid4(),
            dataset_id=dataset.id,
            version=version_number,
            content_hash=dataset_content_hash(items, metadata),
            item_count=len(items),
            version_metadata=metadata,
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        self.repository.add(version)
        await self.session.flush()
        self.repository.add_items(
            [
                DatasetItem(
                    id=uuid4(),
                    dataset_version_id=version.id,
                    ordinal=ordinal,
                    input=item.input,
                    expected_output=item.expected_output,
                    expected_tools=item.expected_tools,
                    context=item.context,
                    item_metadata=item.metadata,
                )
                for ordinal, item in enumerate(items, start=1)
            ]
        )
        await self.session.flush()
        return version
