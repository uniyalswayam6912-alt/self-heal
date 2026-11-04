import httpx
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

def get_retry_delay(headers: dict, default_delay: int = 2) -> int:
    retry_after = headers.get("Retry-After")

    if not retry_after:
        return default_delay

    try:
        return max(0, int(retry_after))
    except ValueError:
        try:
            retry_date = parsedate_to_datetime(retry_after)

            if retry_date.tzinfo is None:
                retry_date = retry_date.replace(tzinfo=timezone.utc)

            delay = (
                retry_date - datetime.now(timezone.utc)
            ).total_seconds()

            return max(0, int(delay))

        except (TypeError, ValueError, OverflowError):
            return default_delay

def send_api_request_with_retry(
    base_url: str,
    method: str,
    endpoint: str,
    headers: dict | None = None,
    payload: dict | None = None,
    params: dict | None = None,
    timeout: float = 10.0,
    max_retries: int = 3,
):
    for attempt in range(max_retries + 1):

        try:
            response = send_api_request(
                base_url=base_url,
                method=method,
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                params=params,
                timeout=timeout,
            )

        except httpx.TimeoutException as error:
            if attempt == max_retries:
                error.retry_count = attempt
                raise

            time.sleep(2 ** (attempt + 1))
            continue

        except httpx.RequestError as error:
            if attempt == max_retries:
                error.retry_count = attempt
                raise

            time.sleep(2 ** (attempt + 1))
            continue


        if response["status_code"] != 429:
            response["retry_count"] = attempt
            return response

        if attempt == max_retries:
            response["retry_count"] = attempt
            return response

        delay = get_retry_delay(response["headers"])
        time.sleep(min(delay, 60))

    return response

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

    start_time = time.perf_counter()

    with httpx.Client(timeout=timeout) as client:
        response = client.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=payload,
        )

    response_time_ms = (
        time.perf_counter() - start_time
    ) * 1000

    try:
        response_data = response.json()
    except ValueError:
        response_data = response.text

    return {
        "status_code": response.status_code,
        "success": response.is_success,
        "data": response_data,
        "headers": dict(response.headers),
        "response_time_ms": round(response_time_ms, 2),
    }