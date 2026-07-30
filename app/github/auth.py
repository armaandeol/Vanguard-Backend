import asyncio
import calendar
import time

import httpx
import jwt

from app import config

_token_cache: dict[str, dict] = {}
_lock = asyncio.Lock()


def _read_private_key() -> str:
    with open(config.GITHUB_PRIVATE_KEY_PATH, "r") as f:
        return f.read()


def _generate_app_jwt() -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": config.GITHUB_APP_ID,
    }
    return jwt.encode(payload, _read_private_key(), algorithm="RS256")


async def get_installation_token(installation_id: str) -> str:
    """Return a cached installation access token, refreshing it if it's near expiry."""
    cached = _token_cache.get(installation_id)
    if cached and cached["expires_at"] - time.time() > 60:
        return cached["token"]

    async with _lock:
        cached = _token_cache.get(installation_id)
        if cached and cached["expires_at"] - time.time() > 60:
            return cached["token"]

        app_jwt = _generate_app_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        resp.raise_for_status()
        data = resp.json()

        expires_at = calendar.timegm(time.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ"))
        _token_cache[installation_id] = {"token": data["token"], "expires_at": expires_at}
        return data["token"]
