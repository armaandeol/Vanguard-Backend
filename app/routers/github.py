import hashlib
import hmac
import logging
import secrets

import httpx
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

    # The uninstall webhook should already clean these up, but webhook delivery
    # isn't guaranteed (tunnel down, missed event, etc.), so double-check live
    # against GitHub and self-heal any installation that's actually gone.
    valid_installations = []
    for doc in docs:
        installation_id = doc.id
        try:
            await get_installation_token(installation_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 401):
                logger.info("Installation %s no longer valid on GitHub, removing", installation_id)
                doc.reference.delete()
                continue
            raise
        valid_installations.append(doc.to_dict())

    return valid_installations


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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
    elif x_github_event == "installation_repositories" and payload.get("action") in ("added", "removed"):
        installation_id = str(payload.get("installation", {}).get("id", ""))
        if installation_id:
            background_tasks.add_task(sync_installation_repositories, installation_id, payload)

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


async def _backfill_repo(token: str, installation_id: str, repo: dict) -> None:
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
        return

    for pr in pulls:
        _store_pull_request(pr=pr, repo=full_name)


async def backfill_installation_commits(installation_id: str) -> None:
    installation_ref = db.collection("installations").document(installation_id)
    installation_ref.set({"syncStatus": "syncing"}, merge=True)

    try:
        token = await get_installation_token(installation_id)
        repos = await list_installation_repositories(token)

        for repo in repos:
            await _backfill_repo(token, installation_id, repo)
    except Exception:
        logger.exception("Backfill failed for installation %s", installation_id)
        installation_ref.set({"syncStatus": "failed"}, merge=True)
        return

    installation_ref.set(
        {"syncStatus": "completed", "syncedAt": firebase_firestore.SERVER_TIMESTAMP}, merge=True
    )


async def sync_installation_repositories(installation_id: str, payload: dict) -> None:
    """Handle repos being added/removed from an existing installation via GitHub's
    'Configure' UI - keep Firestore's repos collection in sync with what's actually
    granted, instead of only ever growing on initial connect."""
    action = payload.get("action")

    try:
        token = await get_installation_token(installation_id)
    except Exception:
        logger.exception("Failed to get installation token for %s during repo sync", installation_id)
        return

    if action == "added":
        added_full_names = {r["full_name"] for r in payload.get("repositories_added", [])}
        if not added_full_names:
            return
        try:
            all_repos = await list_installation_repositories(token)
        except Exception:
            logger.exception("Failed to list repos for installation %s", installation_id)
            return
        for repo in all_repos:
            if repo["full_name"] in added_full_names:
                await _backfill_repo(token, installation_id, repo)

    elif action == "removed":
        for minimal_repo in payload.get("repositories_removed", []):
            full_name = minimal_repo.get("full_name")
            if not full_name:
                continue
            db.collection("repos").document(sanitize_doc_id(full_name)).delete()
            logger.info("Repo %s removed from installation %s, deleted from Firestore", full_name, installation_id)
