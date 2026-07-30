import httpx

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def list_installation_repositories(token: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/installation/repositories",
            headers=_headers(token),
            params={"per_page": 100},
        )
    resp.raise_for_status()
    return resp.json().get("repositories", [])


async def list_repo_commits(token: str, owner: str, repo: str, per_page: int = 100) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits",
            headers=_headers(token),
            params={"per_page": per_page},
        )
    resp.raise_for_status()
    return resp.json()


async def list_repo_pulls(token: str, owner: str, repo: str, per_page: int = 100) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=_headers(token),
            params={"per_page": per_page, "state": "all"},
        )
    resp.raise_for_status()
    return resp.json()


async def list_repo_branches(token: str, owner: str, repo: str, per_page: int = 100) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/branches",
            headers=_headers(token),
            params={"per_page": per_page},
        )
    resp.raise_for_status()
    return resp.json()


async def get_pr_files(token: str, owner: str, repo: str, pr_number: int, per_page: int = 100) -> list[dict]:
    """Paginated fetch of a PR's changed files, including unified diff patches."""
    files: list[dict] = []
    page = 1
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=_headers(token),
                params={"per_page": per_page, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
    return files


async def create_check_run(token: str, owner: str, repo: str, payload: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/check-runs",
            headers=_headers(token),
            json=payload,
        )
    resp.raise_for_status()
    return resp.json()


async def update_check_run(token: str, owner: str, repo: str, check_run_id: int, payload: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}/check-runs/{check_run_id}",
            headers=_headers(token),
            json=payload,
        )
    resp.raise_for_status()
    return resp.json()
