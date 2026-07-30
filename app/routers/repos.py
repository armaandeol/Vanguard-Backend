import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from google.cloud.firestore_v1.base_query import FieldFilter

from app.auth import get_current_user
from app.firebase import db
from app.github.auth import get_installation_token
from app.github.client import list_repo_branches
from app.utils import sanitize_doc_id

logger = logging.getLogger("deployiq.repos")

router = APIRouter(tags=["repos"])


def _user_installation_ids(firebase_uid: str) -> list[str]:
    docs = (
        db.collection("installations")
        .where(filter=FieldFilter("firebaseUserId", "==", firebase_uid))
        .stream()
    )
    return [doc.id for doc in docs]


def _get_owned_repo(repo_full_name: str, installation_ids: list[str]) -> dict:
    doc = db.collection("repos").document(sanitize_doc_id(repo_full_name)).get()
    if not doc.exists or doc.to_dict().get("installationId") not in installation_ids:
        raise HTTPException(status_code=404, detail="Repository not found")
    return doc.to_dict()


@router.get("/repos")
async def list_repos(decoded_token: dict = Depends(get_current_user)):
    installation_ids = _user_installation_ids(decoded_token["uid"])
    if not installation_ids:
        return []

    repos = []
    for i in range(0, len(installation_ids), 10):
        chunk = installation_ids[i : i + 10]
        docs = (
            db.collection("repos")
            .where(filter=FieldFilter("installationId", "in", chunk))
            .stream()
        )
        repos.extend(doc.to_dict() for doc in docs)
    return repos


@router.get("/repos/{repo_full_name:path}/stats")
async def repo_stats(repo_full_name: str, decoded_token: dict = Depends(get_current_user)):
    installation_ids = _user_installation_ids(decoded_token["uid"])
    _get_owned_repo(repo_full_name, installation_ids)

    docs = (
        db.collection("commits")
        .where(filter=FieldFilter("repo", "==", repo_full_name))
        .stream()
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    by_author: dict[str, dict] = {}
    total_commits = 0

    for doc in docs:
        commit = doc.to_dict()
        author = commit.get("author") or "Unknown"
        total_commits += 1
        stats = by_author.setdefault(author, {"author": author, "totalCommits": 0, "commitsLast7Days": 0})
        stats["totalCommits"] += 1

        recent = False
        timestamp = commit.get("timestamp")
        if timestamp:
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                recent = parsed >= cutoff
            except ValueError:
                recent = False
        if recent:
            stats["commitsLast7Days"] += 1

    contributors = sorted(by_author.values(), key=lambda s: s["totalCommits"], reverse=True)

    return {"repo": repo_full_name, "totalCommits": total_commits, "contributors": contributors}


@router.get("/repos/{repo_full_name:path}/pull_requests")
async def repo_pull_requests(repo_full_name: str, decoded_token: dict = Depends(get_current_user)):
    installation_ids = _user_installation_ids(decoded_token["uid"])
    _get_owned_repo(repo_full_name, installation_ids)

    docs = (
        db.collection("pull_requests")
        .where(filter=FieldFilter("repo", "==", repo_full_name))
        .stream()
    )
    pull_requests = [doc.to_dict() for doc in docs]
    pull_requests.sort(key=lambda pr: pr.get("createdAt") or "", reverse=True)
    return pull_requests


@router.get("/repos/{repo_full_name:path}/branches")
async def repo_branches(repo_full_name: str, decoded_token: dict = Depends(get_current_user)):
    installation_ids = _user_installation_ids(decoded_token["uid"])
    repo = _get_owned_repo(repo_full_name, installation_ids)

    token = await get_installation_token(repo["installationId"])
    owner, name = repo_full_name.split("/", 1)
    branches = await list_repo_branches(token, owner, name)

    return [
        {
            "name": branch["name"],
            "htmlUrl": f"https://github.com/{repo_full_name}/tree/{branch['name']}",
        }
        for branch in branches
    ]
