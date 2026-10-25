import json
import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AppError, NotFoundError
from agentscope_api.models import Dataset, DatasetItem, DatasetVersion
from agentscope_api.repositories.datasets import DatasetRepository
from agentscope_api.schemas.datasets import (
    DatasetAppendCase,
    DatasetCreate,
    DatasetImportFormat,
    DatasetItemResponse,
    DatasetResponse,
    DatasetVersionCreate,
    DatasetVersionPage,
    DatasetVersionSummary,
    PageMetadata,
)
from agentscope_api.services.authorization import Permission, require_permission
from agentscope_api.services.datasets import DatasetService

router = APIRouter(tags=["Datasets"])


def _version_response(version: DatasetVersion) -> DatasetVersionSummary:
    return DatasetVersionSummary(
        id=version.id,
        dataset_id=version.dataset_id,
        version=version.version,
        content_hash=version.content_hash,
        item_count=version.item_count,
        metadata=version.version_metadata,
        created_at=version.created_at,
    )


def _dataset_response(dataset: Dataset, versions: list[DatasetVersion]) -> DatasetResponse:
    if not versions:
        raise RuntimeError("Dataset has no immutable versions")
    return DatasetResponse(
        id=dataset.id,
        organization_id=dataset.organization_id,
        project_id=dataset.project_id,
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        latest_version=_version_response(versions[0]),
        versions=[_version_response(version) for version in versions],
    )


def _item_response(item: DatasetItem) -> DatasetItemResponse:
    return DatasetItemResponse(
        id=item.id,
        dataset_version_id=item.dataset_version_id,
        ordinal=item.ordinal,
        input=item.input,
        expected_output=item.expected_output,
        expected_tools=item.expected_tools,
        context=item.context,
        metadata=item.item_metadata,
    )


async def _detail(
    repository: DatasetRepository, dataset_id: UUID, project_id: UUID
) -> tuple[Dataset, list[DatasetVersion]]:
    dataset = await repository.get_dataset(dataset_id, project_id)
    if dataset is None:
        raise NotFoundError("Dataset")
    versions = await repository.list_versions(dataset.id)
    return dataset, versions


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetResponse])
async def list_datasets(
    access: ProjectAccessDependency, session: SessionDependency
) -> list[DatasetResponse]:
    require_permission(access.membership.role, Permission.DATASET_READ)
    rows = await DatasetRepository(session).list_datasets(access.project.id)
    return [_dataset_response(dataset, versions) for dataset, versions in rows]


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    payload: DatasetCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> DatasetResponse:
    dataset, _ = await DatasetService(session, settings).create_dataset(
        access.project, access.membership, payload, user
    )
    versions = await DatasetRepository(session).list_versions(dataset.id)
    return _dataset_response(dataset, versions)


@router.get("/projects/{project_id}/datasets/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
) -> DatasetResponse:
    require_permission(access.membership.role, Permission.DATASET_READ)
    dataset, versions = await _detail(DatasetRepository(session), dataset_id, access.project.id)
    return _dataset_response(dataset, versions)


@router.post(
    "/projects/{project_id}/datasets/{dataset_id}/versions",
    response_model=DatasetVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset_version(
    dataset_id: UUID,
    payload: DatasetVersionCreate,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> DatasetVersionSummary:
    version = await DatasetService(session, settings).create_version(
        access.project, access.membership, dataset_id, payload, user
    )
    return _version_response(version)


@router.post(
    "/projects/{project_id}/datasets/{dataset_id}/items",
    response_model=DatasetVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def append_dataset_case(
    dataset_id: UUID,
    payload: DatasetAppendCase,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
) -> DatasetVersionSummary:
    version = await DatasetService(session, settings).append_case(
        access.project, access.membership, dataset_id, payload, user
    )
    return _version_response(version)


@router.post(
    "/projects/{project_id}/datasets/{dataset_id}/versions/import",
    response_model=DatasetVersionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def import_dataset_version(
    dataset_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    user: CurrentUser,
    import_format: Annotated[DatasetImportFormat, Form(alias="format")],
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form()] = "{}",
) -> DatasetVersionSummary:
    require_permission(access.membership.role, Permission.DATASET_MANAGE)
    try:
        parsed_metadata = json.loads(metadata)
    except json.JSONDecodeError as error:
        raise AppError(
            "INVALID_DATASET_METADATA",
            "Import metadata must be valid JSON",
            status_code=422,
        ) from error
    if not isinstance(parsed_metadata, dict):
        raise AppError(
            "INVALID_DATASET_METADATA",
            "Import metadata must be a JSON object",
            status_code=422,
        )
    content = await file.read(settings.dataset_max_import_bytes + 1)
    await file.close()
    version = await DatasetService(session, settings).create_import_version(
        access.project,
        access.membership,
        dataset_id,
        content=content,
        import_format=import_format,
        metadata={
            **parsed_metadata,
            "import_filename": file.filename,
            "import_format": import_format,
        },
        user=user,
    )
    return _version_response(version)


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}/versions/{version_number}",
    response_model=DatasetVersionPage,
)
async def get_dataset_version(
    dataset_id: UUID,
    version_number: int,
    access: ProjectAccessDependency,
    session: SessionDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> DatasetVersionPage:
    require_permission(access.membership.role, Permission.DATASET_READ)
    repository = DatasetRepository(session)
    dataset = await repository.get_dataset(dataset_id, access.project.id)
    if dataset is None:
        raise NotFoundError("Dataset")
    version = await repository.get_version(dataset.id, version_number)
    if version is None:
        raise NotFoundError("Dataset version")
    total_pages = max(1, math.ceil(version.item_count / page_size))
    if page > total_pages:
        raise AppError(
            "INVALID_PAGE",
            "Requested page exceeds the dataset version page count",
            status_code=422,
            details={"total_pages": total_pages},
        )
    items = await repository.list_items(version.id, offset=(page - 1) * page_size, limit=page_size)
    return DatasetVersionPage(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        version=_version_response(version),
        items=[_item_response(item) for item in items],
        pagination=PageMetadata(
            page=page,
            page_size=page_size,
            total_items=version.item_count,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )
