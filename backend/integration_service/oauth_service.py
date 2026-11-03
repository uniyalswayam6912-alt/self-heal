import httpx


def refresh_oauth_token(
    token_url: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
):
    response = httpx.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10.0,
    )

    response.raise_for_status()

    return response.json()
