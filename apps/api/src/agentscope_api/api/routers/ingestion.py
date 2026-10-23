from fastapi import APIRouter, Request, status

from agentscope_api.api.dependencies import (
    IngestionAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AppError
from agentscope_api.core.rate_limit import enforce_ingestion_rate_limit
from agentscope_api.schemas.tracing import IngestionBatch, IngestionResponse
from agentscope_api.services.ingestion import IngestionService

router = APIRouter(prefix="/v1/ingest", tags=["Telemetry ingestion"])


@router.post("/batch", response_model=IngestionResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(
    payload: IngestionBatch,
    request: Request,
    access: IngestionAccessDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> IngestionResponse:
    await enforce_ingestion_rate_limit(access.api_key.id, settings)
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError as error:
        raise AppError(
            "INVALID_CONTENT_LENGTH", "Content-Length is invalid", status_code=400
        ) from error
    return await IngestionService(session, settings).ingest(payload, access, content_length)
