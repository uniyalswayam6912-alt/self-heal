import httpx


def send_api_request(
    base_url: str,
    method: str,
    endpoint: str,
    headers: dict | None = None,
    payload: dict | None = None,
    params: dict | None = None,
    timeout: float = 10.0,
):
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    with httpx.Client(timeout=timeout) as client:
        response = client.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=payload,
        )

    try:
        response_data = response.json()
    except ValueError:
        response_data = response.text

    return {
        "status_code": response.status_code,
        "success": response.is_success,
        "data": response_data,
    }