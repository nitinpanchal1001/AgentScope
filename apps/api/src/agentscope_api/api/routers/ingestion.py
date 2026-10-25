from fastapi import APIRouter, BackgroundTasks, Request, status

from agentscope_api.api.dependencies import (
    IngestionAccessDependency,
    SessionDependency,
    SettingsDependency,
)
from agentscope_api.core.exceptions import AppError
from agentscope_api.core.metrics import INGESTION_BATCHES, INGESTION_EVENTS
from agentscope_api.core.rate_limit import enforce_ingestion_rate_limit
from agentscope_api.schemas.tracing import IngestionBatch, IngestionResponse
from agentscope_api.services.evaluation_dispatch import dispatch_evaluation
from agentscope_api.services.failure_dispatch import dispatch_failure_analysis
from agentscope_api.services.ingestion import IngestionService

router = APIRouter(prefix="/v1/ingest", tags=["Telemetry ingestion"])


@router.post("/batch", response_model=IngestionResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(
    payload: IngestionBatch,
    request: Request,
    background_tasks: BackgroundTasks,
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
    service = IngestionService(session, settings)
    try:
        response = await service.ingest(payload, access, content_length)
    except Exception:
        INGESTION_BATCHES.labels("failed").inc()
        raise
    INGESTION_BATCHES.labels("accepted").inc()
    INGESTION_EVENTS.labels("accepted").inc(response.accepted)
    INGESTION_EVENTS.labels("duplicate").inc(response.duplicates)
    for result_id in service.pending_evaluation_dispatches:
        background_tasks.add_task(dispatch_evaluation, result_id)
    for trace_id in service.pending_failure_dispatches:
        background_tasks.add_task(dispatch_failure_analysis, trace_id)
    return response
