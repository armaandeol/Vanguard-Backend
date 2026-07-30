import hashlib
import hmac
import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from firebase_admin import firestore as firebase_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app import config
from app.auth import get_current_user
from app.firebase import db
from app.github.auth import get_installation_token
from app.github.client import list_installation_repositories, list_repo_commits, list_repo_pulls
from app.utils import sanitize_doc_id

logger = logging.getLogger("deployiq.github")

router = APIRouter(tags=["github"])


@router.get("/auth/github/connect")
async def github_connect(decoded_token: dict = Depends(get_current_user)):
    """Return the GitHub App install URL for the signed-in user to be redirected to."""
    state = secrets.token_urlsafe(32)
    db.collection("github_oauth_states").document(state).set(
        {
            "firebaseUserId": decoded_token["uid"],
            "createdAt": firebase_firestore.SERVER_TIMESTAMP,
        }
    )
    install_url = f"https://github.com/apps/{config.GITHUB_APP_SLUG}/installations/new?state={state}"
    return {"install_url": install_url}


@router.get("/auth/github/callback")
async def github_callback(
    background_tasks: BackgroundTasks,
    installation_id: str,
    state: str,
    setup_action: str | None = None,
):
    state_ref = db.collection("github_oauth_states").document(state)
    state_doc = state_ref.get()
    if not state_doc.exists:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    firebase_uid = state_doc.to_dict()["firebaseUserId"]
    state_ref.delete()

    db.collection("installations").document(installation_id).set(
        {
            "installationId": installation_id,
            "firebaseUserId": firebase_uid,
            "connectedAt": firebase_firestore.SERVER_TIMESTAMP,
            "status": "active",
            "syncStatus": "pending",
        }
    )

    logger.info("GitHub installation %s connected (setup_action=%s)", installation_id, setup_action)
    background_tasks.add_task(backfill_installation_commits, installation_id)

    return RedirectResponse(url=f"{config.FRONTEND_URL}/dashboard")


@router.get("/github/installations")
async def list_installations(decoded_token: dict = Depends(get_current_user)):
    docs = (
        db.collection("installations")
        .where(filter=FieldFilter("firebaseUserId", "==", decoded_token["uid"]))
        .stream()
    )
    return [doc.to_dict() for doc in docs]


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str = Header(...),
):
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)
    payload = await request.json()

    logger.info("GitHub webhook received: event=%s payload=%s", x_github_event, payload)

    repo_full_name = payload.get("repository", {}).get("full_name")

    if x_github_event == "push":
        for commit in payload.get("commits", []):
            _store_commit(
                sha=commit.get("id"),
                author=commit.get("author", {}).get("name"),
                timestamp=commit.get("timestamp"),
                repo=repo_full_name,
                event="push",
            )
    elif x_github_event == "pull_request":
        pr = payload.get("pull_request", {})
        _store_commit(
            sha=pr.get("head", {}).get("sha"),
            author=pr.get("user", {}).get("login"),
            timestamp=pr.get("updated_at"),
            repo=repo_full_name,
            event="pull_request",
        )
        _store_pull_request(pr=pr, repo=repo_full_name)
    elif x_github_event == "installation" and payload.get("action") == "deleted":
        installation_id = str(payload.get("installation", {}).get("id", ""))
        if installation_id:
            db.collection("installations").document(installation_id).delete()
            logger.info("GitHub installation %s uninstalled, removed from Firestore", installation_id)

    return {"received": True}


def _verify_signature(body: bytes, signature_header: str) -> None:
    if not config.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = "sha256=" + hmac.new(
        config.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _store_commit(*, sha: str | None, author: str | None, timestamp: str | None, repo: str | None, event: str) -> None:
    if not sha:
        return
    db.collection("commits").document(sha).set(
        {"sha": sha, "author": author, "timestamp": timestamp, "repo": repo, "event": event},
        merge=True,
    )


def _pr_state(pr: dict) -> str:
    # The "list pull requests" API only sets merged_at (no "merged" bool, unlike
    # the single-PR / webhook payload shapes), so key off that instead.
    if pr.get("state") == "closed" and (pr.get("merged") or pr.get("merged_at")):
        return "merged"
    return pr.get("state", "open")


def _store_pull_request(*, pr: dict, repo: str | None) -> None:
    number = pr.get("number")
    if not repo or number is None:
        return
    db.collection("pull_requests").document(f"{sanitize_doc_id(repo)}_{number}").set(
        {
            "prNumber": number,
            "title": pr.get("title"),
            "state": _pr_state(pr),
            "author": pr.get("user", {}).get("login"),
            "htmlUrl": pr.get("html_url"),
            "repo": repo,
            "createdAt": pr.get("created_at"),
            "updatedAt": pr.get("updated_at"),
        },
        merge=True,
    )


def _store_repo(*, installation_id: str, repo: dict) -> None:
    db.collection("repos").document(sanitize_doc_id(repo["full_name"])).set(
        {
            "installationId": installation_id,
            "fullName": repo["full_name"],
            "defaultBranch": repo.get("default_branch"),
            "htmlUrl": repo.get("html_url"),
            "connectedAt": firebase_firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


async def backfill_installation_commits(installation_id: str) -> None:
    installation_ref = db.collection("installations").document(installation_id)
    installation_ref.set({"syncStatus": "syncing"}, merge=True)

    try:
        token = await get_installation_token(installation_id)
        repos = await list_installation_repositories(token)

        for repo in repos:
            full_name = repo["full_name"]
            _store_repo(installation_id=installation_id, repo=repo)

            try:
                commits = await list_repo_commits(token, repo["owner"]["login"], repo["name"])
            except Exception:
                logger.exception("Failed to backfill commits for %s", full_name)
                commits = []

            for commit in commits:
                author_info = commit.get("commit", {}).get("author", {})
                _store_commit(
                    sha=commit.get("sha"),
                    author=author_info.get("name"),
                    timestamp=author_info.get("date"),
                    repo=full_name,
                    event="backfill",
                )

            try:
                pulls = await list_repo_pulls(token, repo["owner"]["login"], repo["name"])
            except Exception:
                logger.exception("Failed to backfill pull requests for %s", full_name)
                continue

            for pr in pulls:
                _store_pull_request(pr=pr, repo=full_name)
    except Exception:
        logger.exception("Backfill failed for installation %s", installation_id)
        installation_ref.set({"syncStatus": "failed"}, merge=True)
        return

    installation_ref.set(
        {"syncStatus": "completed", "syncedAt": firebase_firestore.SERVER_TIMESTAMP}, merge=True
    )
