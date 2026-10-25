from httpx import AsyncClient


async def test_metrics_expose_bounded_http_and_ingestion_series(client: AsyncClient) -> None:
    await client.get("/health/live")
    await client.get("/definitely-not-a-route")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "agentscope_http_requests_total" in response.text
    assert 'route="/health/live"' in response.text
    assert 'route="unmatched"' in response.text
    assert "agentscope_http_request_duration_seconds_bucket" in response.text
    assert "agentscope_ingestion_batches_total" in response.text
