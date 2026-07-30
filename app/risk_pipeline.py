"""
Webhook-triggered PR risk analysis pipeline.

Orchestrates the same feature-extraction -> XGBoost -> Gemini -> RAG flow that
`pr_detector.py` runs as a standalone CLI, but triggered from the live GitHub
webhook (`app/routers/github.py`) instead of a polling loop. Results are
persisted to the `risk_reports` Firestore collection and posted back onto the
PR as a GitHub Check Run (using the GitHub App's own installation token, so
the check shows up under the App's identity rather than a personal token).

All the heavy classes (GitFeatureExtractor, MLModelRiskAnalyzer,
GeminiRiskAnalyzer, LocalRepoManager) are imported directly from
`pr_detector.py` rather than reimplemented here.
"""

import asyncio
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from firebase_admin import firestore as firebase_firestore

from app import config
from app.firebase import db
from app.github.auth import get_installation_token
from app.github.client import create_check_run, get_pr_files, update_check_run
from app.pr_detector import (
    FeatureVector,
    FileChange,
    GeminiRiskAnalyzer,
    GitFeatureExtractor,
    LocalRepoManager,
    MLModelRiskAnalyzer,
    PRDetails,
)
from app.utils import sanitize_doc_id

logger = logging.getLogger("deployiq.risk_pipeline")

CHECK_RUN_NAME = "Vanguard Deployment Risk"

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_APP_DIR)
_LOCAL_REPOS_DIR = os.path.join(_BACKEND_ROOT, "local_repos")

# Mirrors the sys.path bootstrap pr_detector.py uses to reach the RAG package
# (RAG/agent.py, RAG/schemas.py, RAG/tools.py are written as top-level scripts,
# not a proper subpackage, so they need their own directory on sys.path).
_RAG_DIR = os.path.join(_APP_DIR, "RAG")
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)

from schemas import AgentInput as RagAgentInput  # noqa: E402
from agent import run_agent  # noqa: E402
import ingest as rag_ingest  # noqa: E402


def ensure_knowledge_base_ready() -> None:
    """Build the Chroma KB collection if it hasn't been ingested yet.

    `start.sh` does this on first-time setup for the CLI path, but the FastAPI
    app can also be launched directly (uvicorn/main.py), which skips that
    bootstrap entirely and would otherwise fail every RAG call with a
    RuntimeError until someone remembers to run `python ingest.py` by hand.
    """
    try:
        rag_ingest.get_client().get_collection(rag_ingest.COLLECTION_NAME)
        return
    except Exception:
        pass

    logger.info("RAG knowledge base not found, ingesting from %s", rag_ingest.KB_DIR)
    try:
        total = rag_ingest.ingest()
        logger.info("Ingested %d knowledge base chunks into '%s'", total, rag_ingest.COLLECTION_NAME)
    except Exception:
        logger.exception(
            "Failed to auto-ingest RAG knowledge base; RAG stage will keep failing "
            "until `python ingest.py` is run manually from app/RAG"
        )


# --------------------------------------------------------------------------- #
# Lazy singletons for the ML model + Gemini client (expensive to construct,
# must not be reloaded per PR; guarded for concurrent first-use from the
# threadpool asyncio.to_thread hands work off to).
# --------------------------------------------------------------------------- #

_ml_analyzer: Optional[MLModelRiskAnalyzer] = None
_ml_analyzer_failed = False
_ml_analyzer_lock = threading.Lock()

_gemini_analyzer: Optional[GeminiRiskAnalyzer] = None
_gemini_analyzer_failed = False
_gemini_analyzer_lock = threading.Lock()


def _get_ml_analyzer() -> Optional[MLModelRiskAnalyzer]:
    global _ml_analyzer, _ml_analyzer_failed
    if _ml_analyzer is not None or _ml_analyzer_failed:
        return _ml_analyzer
    with _ml_analyzer_lock:
        if _ml_analyzer is not None or _ml_analyzer_failed:
            return _ml_analyzer
        try:
            _ml_analyzer = MLModelRiskAnalyzer()
        except Exception:
            logger.exception("Failed to load ML risk model; ML scoring disabled")
            _ml_analyzer_failed = True
    return _ml_analyzer


def _get_gemini_analyzer() -> Optional[GeminiRiskAnalyzer]:
    global _gemini_analyzer, _gemini_analyzer_failed
    if _gemini_analyzer is not None or _gemini_analyzer_failed:
        return _gemini_analyzer
    with _gemini_analyzer_lock:
        if _gemini_analyzer is not None or _gemini_analyzer_failed:
            return _gemini_analyzer
        try:
            _gemini_analyzer = GeminiRiskAnalyzer()
        except Exception:
            logger.exception("Failed to init Gemini risk analyzer; LLM scoring disabled")
            _gemini_analyzer_failed = True
    return _gemini_analyzer


# --------------------------------------------------------------------------- #
# Per-repo lock so overlapping webhook deliveries (e.g. rapid-fire pushes)
# never fetch/write the same local clone concurrently.
# --------------------------------------------------------------------------- #

_repo_locks: dict[str, asyncio.Lock] = {}


def _lock_for_repo(repo_full_name: str) -> asyncio.Lock:
    lock = _repo_locks.get(repo_full_name)
    if lock is None:
        lock = asyncio.Lock()
        _repo_locks[repo_full_name] = lock
    return lock


# --------------------------------------------------------------------------- #
# Payload -> PRDetails
# --------------------------------------------------------------------------- #


def _pr_details_from_payload(pr_payload: dict, files_raw: list[dict]) -> PRDetails:
    files = [
        FileChange(
            filename=f["filename"],
            status=f["status"],
            additions=f["additions"],
            deletions=f["deletions"],
            changes=f["changes"],
            patch=f.get("patch"),
        )
        for f in files_raw
    ]
    return PRDetails(
        number=pr_payload["number"],
        title=pr_payload.get("title") or "",
        author=pr_payload.get("user", {}).get("login") or "unknown",
        state=pr_payload.get("state") or "open",
        created_at=pr_payload.get("created_at"),
        updated_at=pr_payload.get("updated_at"),
        base_branch=pr_payload["base"]["ref"],
        head_branch=pr_payload["head"]["ref"],
        additions=pr_payload.get("additions", 0),
        deletions=pr_payload.get("deletions", 0),
        changed_files=pr_payload.get("changed_files", len(files)),
        commits=pr_payload.get("commits", 0),
        url=pr_payload.get("html_url") or "",
        files=files,
    )


# --------------------------------------------------------------------------- #
# The synchronous pipeline (clone/fetch + feature extraction + ML + Gemini +
# RAG are all blocking calls) -- run via asyncio.to_thread so it never blocks
# the FastAPI event loop.
# --------------------------------------------------------------------------- #


def _run_rag_agent(ml_result: dict, code_review_finding: dict) -> dict:
    """Builds the RAG AgentInput and runs the agent, mirroring the payload shape
    pr_detector.py's own _run_risk_analysis sends to the RAG pipeline."""
    contributions = ml_result["shap_explanation"]["top_contributions"]
    formatted_contributions = [
        {
            "feature_name": c["feature_name"],
            "raw_value": c["feature_value"],
            "shap_value": c["shap_value"],
            "direction": c["direction"],
            "rank": i + 1,
        }
        for i, c in enumerate(contributions)
    ]

    agent_payload = {
        "ml_result": {
            "feature_vector": ml_result["feature_vector"],
            "shap_explanation": {
                "base_value": ml_result["shap_explanation"]["base_value"],
                "output_value": ml_result["shap_explanation"]["output_value"],
                "contributions": formatted_contributions,
            },
        },
        "code_review_finding": code_review_finding,
    }

    agent_input = RagAgentInput.model_validate(agent_payload)
    result = run_agent(agent_input)
    return result.report.model_dump()


def _run_sync_pipeline(details: PRDetails, owner: str, repo_name: str, token: str) -> dict:
    repo_manager = LocalRepoManager(
        owner,
        repo_name,
        local_path=os.path.join(_LOCAL_REPOS_DIR, f"{owner}_{repo_name}"),
        token=token,
    )
    local_repo = repo_manager.get_repo()

    feature_extractor = GitFeatureExtractor(local_repo)
    fv: FeatureVector = feature_extractor.extract(details)

    ml_analyzer = _get_ml_analyzer()
    if ml_analyzer is None:
        raise RuntimeError("ML risk model unavailable")
    ml_result = ml_analyzer.predict(fv)

    gemini_analyzer = _get_gemini_analyzer()
    if gemini_analyzer is None:
        raise RuntimeError("Gemini risk analyzer unavailable")
    code_review_finding = gemini_analyzer.analyze(details, fv)

    report = _run_rag_agent(ml_result, code_review_finding)

    return {
        "feature_vector": fv.to_dict(),
        "ml_result": ml_result,
        "code_review_finding": code_review_finding,
        "report": report,
    }


# --------------------------------------------------------------------------- #
# GitHub Check Run conclusion + output formatting
# --------------------------------------------------------------------------- #


def _conclusion_for_risk(deployment_risk: Optional[str]) -> str:
    return {"LOW": "success", "MEDIUM": "neutral", "HIGH": "action_required"}.get(
        deployment_risk or "", "neutral"
    )


def _bullets(items: list) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def _build_check_output(report: dict, feature_vector: dict, ml_result: dict) -> dict:
    risk = report.get("deployment_risk", "UNKNOWN")
    probability = report.get("bug_probability") or 0.0
    title = f"{risk} risk — {probability * 100:.0f}% estimated bug probability"

    summary = "\n\n".join(
        [
            f"**Deployment risk: {risk}**  \nEstimated bug probability: {probability * 100:.1f}%",
            "### ML explanation",
            _bullets(report.get("ml_explanation", [])),
            "### Code review findings",
            _bullets(report.get("code_review_findings", [])),
            "### Engineering guidance",
            _bullets(report.get("engineering_guidance", [])),
            "### Recommended actions",
            _bullets(report.get("recommended_actions", [])),
            "### Sources consulted",
            _bullets(report.get("sources_consulted", [])),
        ]
    )

    contributions = ml_result.get("shap_explanation", {}).get("top_contributions", [])
    contrib_rows = "\n".join(
        f"| {c['feature_name']} | {c['feature_value']} | {c['shap_value']:+.4f} | {c['direction']} |"
        for c in contributions
    ) or "| (none) | | | |"
    feature_rows = "\n".join(f"| {name} | {value} |" for name, value in feature_vector.items())

    text = (
        "<details>\n<summary>Raw feature vector</summary>\n\n"
        "| Feature | Value |\n| --- | --- |\n" + feature_rows + "\n\n</details>\n\n"
        "<details>\n<summary>SHAP contributions</summary>\n\n"
        "| Feature | Value | SHAP | Direction |\n| --- | --- | --- | --- |\n" + contrib_rows + "\n\n</details>\n\n"
        "_Analysis by Vanguard — automated deployment risk assessment. Not a substitute for human review._"
    )

    return {"title": title, "summary": summary, "text": text}


# --------------------------------------------------------------------------- #
# Firestore persistence
# --------------------------------------------------------------------------- #


def _store_risk_report(repo_full_name: str, pr_number: int, doc: dict) -> None:
    ref = db.collection("risk_reports").document(f"{sanitize_doc_id(repo_full_name)}_{pr_number}")
    existing = ref.get()
    payload = dict(doc)
    payload["updatedAt"] = firebase_firestore.SERVER_TIMESTAMP
    if not existing.exists:
        payload["createdAt"] = firebase_firestore.SERVER_TIMESTAMP
    ref.set(payload, merge=True)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _should_skip_existing(existing_data: Optional[dict], head_sha: str) -> bool:
    """True if a risk_reports doc already covers this exact commit, so a
    redelivered/duplicate webhook (or an overlapping synchronize) shouldn't
    kick off another run."""
    if not existing_data:
        return False
    return existing_data.get("headSha") == head_sha and existing_data.get("status") in ("pending", "completed")


# --------------------------------------------------------------------------- #
# Entry point, scheduled as a BackgroundTask from the webhook handler
# --------------------------------------------------------------------------- #


async def run_risk_pipeline_for_pr(installation_id: str, repo_full_name: str, pr_payload: dict) -> None:
    number = pr_payload.get("number")
    head_sha = pr_payload.get("head", {}).get("sha")
    if not repo_full_name or number is None or not head_sha:
        logger.warning("Skipping risk pipeline: incomplete PR payload for %s", repo_full_name)
        return

    owner, _, repo_name = repo_full_name.partition("/")
    if not owner or not repo_name:
        logger.warning("Skipping risk pipeline: unparsable repo full name %r", repo_full_name)
        return

    doc_ref = db.collection("risk_reports").document(f"{sanitize_doc_id(repo_full_name)}_{number}")

    async with _lock_for_repo(repo_full_name):
        existing = doc_ref.get()
        if existing.exists and _should_skip_existing(existing.to_dict(), head_sha):
            logger.info(
                "Risk report for %s#%s at %s already pending/completed, skipping",
                repo_full_name, number, head_sha[:8],
            )
            return

        try:
            token = await get_installation_token(installation_id)
        except Exception:
            logger.exception("Failed to get installation token for %s", repo_full_name)
            return

        base_doc = {
            "repo": repo_full_name,
            "prNumber": number,
            "title": pr_payload.get("title"),
            "htmlUrl": pr_payload.get("html_url"),
            "author": pr_payload.get("user", {}).get("login"),
            "headSha": head_sha,
        }

        check_run_id = None
        check_run_url = None
        try:
            check_run = await create_check_run(
                token,
                owner,
                repo_name,
                {
                    "name": CHECK_RUN_NAME,
                    "head_sha": head_sha,
                    "status": "in_progress",
                    "started_at": _iso_now(),
                    "details_url": f"{config.FRONTEND_URL}/repos/{quote(repo_full_name, safe='')}",
                },
            )
            check_run_id = check_run.get("id")
            check_run_url = check_run.get("html_url")
        except Exception:
            logger.exception("Failed to create check run for %s#%s", repo_full_name, number)

        _store_risk_report(
            repo_full_name,
            number,
            {**base_doc, "status": "pending", "checkRunId": check_run_id, "checkRunUrl": check_run_url},
        )

        try:
            files_raw = await get_pr_files(token, owner, repo_name, number)
            details = _pr_details_from_payload(pr_payload, files_raw)
            result = await asyncio.to_thread(_run_sync_pipeline, details, owner, repo_name, token)
        except Exception as exc:
            logger.exception("Risk pipeline failed for %s#%s", repo_full_name, number)
            if check_run_id is not None:
                try:
                    await update_check_run(
                        token,
                        owner,
                        repo_name,
                        check_run_id,
                        {
                            "status": "completed",
                            "conclusion": "neutral",
                            "completed_at": _iso_now(),
                            "output": {
                                "title": "Vanguard: analysis incomplete",
                                "summary": (
                                    "The risk analysis pipeline hit an error and could not complete "
                                    "for this PR. This is not a signal about the PR's risk — check "
                                    "the DeployIQ backend logs for details."
                                ),
                            },
                        },
                    )
                except Exception:
                    logger.exception(
                        "Failed to update check run after pipeline failure for %s#%s", repo_full_name, number
                    )
            _store_risk_report(
                repo_full_name,
                number,
                {
                    **base_doc,
                    "status": "failed",
                    "error": type(exc).__name__,
                    "checkRunId": check_run_id,
                    "checkRunUrl": check_run_url,
                },
            )
            return

        report = result["report"]
        conclusion = _conclusion_for_risk(report.get("deployment_risk"))

        if check_run_id is not None:
            try:
                await update_check_run(
                    token,
                    owner,
                    repo_name,
                    check_run_id,
                    {
                        "status": "completed",
                        "conclusion": conclusion,
                        "completed_at": _iso_now(),
                        "output": _build_check_output(report, result["feature_vector"], result["ml_result"]),
                    },
                )
            except Exception:
                logger.exception("Failed to update check run for %s#%s", repo_full_name, number)

        _store_risk_report(
            repo_full_name,
            number,
            {
                **base_doc,
                "status": "completed",
                "deploymentRisk": report.get("deployment_risk"),
                "bugProbability": report.get("bug_probability"),
                "mlExplanation": report.get("ml_explanation", []),
                "codeReviewFindings": report.get("code_review_findings", []),
                "engineeringGuidance": report.get("engineering_guidance", []),
                "recommendedActions": report.get("recommended_actions", []),
                "sourcesConsulted": report.get("sources_consulted", []),
                "featureVector": result["feature_vector"],
                "shapContributions": result["ml_result"]["shap_explanation"]["top_contributions"],
                "checkRunId": check_run_id,
                "checkRunUrl": check_run_url,
                "checkConclusion": conclusion,
            },
        )
