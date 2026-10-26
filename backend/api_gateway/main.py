
from fastapi import FastAPI, Request
from fastapi.responses import Response
import httpx

app = FastAPI(
    title="Self-Heal API Gateway",
    version="0.1.0",
)

SERVICE_URLS = {
    "auth": "http://auth-service:8000",
    "projects": "http://127.0.0.1:8002",
    "jobs": "http://127.0.0.1:8003",
    "workflows": "http://127.0.0.1:8004",
    "notifications": "http://127.0.0.1:8005",
    "reports": "http://127.0.0.1:8006",
    "integrations": "http://127.0.0.1:8007",
}

FORWARDED_METHODS = [
    "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"
]

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


@app.get("/health")
def health_check():
    return {
        "service": "api-gateway",
        "status": "healthy",
    }


async def forward_request(
    service: str,
    path: str,
    request: Request,
):
    service_url = SERVICE_URLS.get(service)

    if service_url is None:
        return {
            "error": "Unknown service",
            "service": service,
        }

    target_url = f"{service_url}/{path}"

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() != "host"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream_response = await client.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                content=await request.body(),
                headers=headers,
            )

    except httpx.RequestError:
        return Response(
            content='{"detail":"Downstream service unavailable"}',
            status_code=502,
            media_type="application/json",
        )

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )


@app.api_route(
    "/{service}",
    methods=FORWARDED_METHODS,
)
async def forward_root(service: str, request: Request):
    return await forward_request(service, "", request)


@app.api_route(
    "/{service}/{path:path}",
    methods=FORWARDED_METHODS,
)
async def forward_path(
    service: str,
    path: str,
    request: Request,
):
    return await forward_request(service, path, request)
