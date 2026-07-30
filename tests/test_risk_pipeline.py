"""Pure-logic tests for app/risk_pipeline.py — no network, Firestore, or GitHub
calls. Model/RAG-dependent behavior is exercised manually per the plan's
webhook-simulation + live-PR verification steps."""

from app.risk_pipeline import (
    _build_check_output,
    _conclusion_for_risk,
    _pr_details_from_payload,
    _should_skip_existing,
)


def test_conclusion_for_risk_maps_each_level():
    assert _conclusion_for_risk("LOW") == "success"
    assert _conclusion_for_risk("MEDIUM") == "neutral"
    assert _conclusion_for_risk("HIGH") == "action_required"


def test_conclusion_for_risk_defaults_to_neutral_for_unknown():
    assert _conclusion_for_risk(None) == "neutral"
    assert _conclusion_for_risk("") == "neutral"
    assert _conclusion_for_risk("NOT_A_LEVEL") == "neutral"


def test_should_skip_existing_true_for_same_head_sha_pending_or_completed():
    assert _should_skip_existing({"headSha": "abc123", "status": "pending"}, "abc123") is True
    assert _should_skip_existing({"headSha": "abc123", "status": "completed"}, "abc123") is True


def test_should_skip_existing_false_for_new_commit():
    assert _should_skip_existing({"headSha": "old_sha", "status": "completed"}, "new_sha") is False


def test_should_skip_existing_false_for_failed_status():
    # A previous failed run for the same commit should be retried, not skipped.
    assert _should_skip_existing({"headSha": "abc123", "status": "failed"}, "abc123") is False


def test_should_skip_existing_false_when_no_prior_doc():
    assert _should_skip_existing(None, "abc123") is False
    assert _should_skip_existing({}, "abc123") is False


def test_pr_details_from_payload_maps_webhook_fields():
    pr_payload = {
        "number": 42,
        "title": "Add feature X",
        "user": {"login": "octocat"},
        "state": "open",
        "created_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-02T00:00:00Z",
        "base": {"ref": "main"},
        "head": {"ref": "feature-x", "sha": "deadbeef"},
        "additions": 10,
        "deletions": 2,
        "changed_files": 1,
        "commits": 3,
        "html_url": "https://github.com/octocat/repo/pull/42",
    }
    files_raw = [
        {
            "filename": "src/x.py",
            "status": "modified",
            "additions": 10,
            "deletions": 2,
            "changes": 12,
            "patch": "@@ -1,2 +1,10 @@\n+new line",
        }
    ]

    details = _pr_details_from_payload(pr_payload, files_raw)

    assert details.number == 42
    assert details.author == "octocat"
    assert details.base_branch == "main"
    assert details.head_branch == "feature-x"
    assert details.additions == 10
    assert details.deletions == 2
    assert len(details.files) == 1
    assert details.files[0].filename == "src/x.py"
    assert details.files[0].patch == "@@ -1,2 +1,10 @@\n+new line"


def test_pr_details_from_payload_falls_back_when_metadata_missing():
    # opened/synchronize payloads always carry these, but keep the mapping
    # defensive rather than KeyError-prone.
    pr_payload = {
        "number": 7,
        "user": {},
        "base": {"ref": "main"},
        "head": {"ref": "fix", "sha": "abc"},
    }
    details = _pr_details_from_payload(pr_payload, [])
    assert details.author == "unknown"
    assert details.title == ""
    assert details.changed_files == 0
    assert details.url == ""


def test_build_check_output_shape():
    report = {
        "deployment_risk": "HIGH",
        "bug_probability": 0.73,
        "ml_explanation": ["High churn in auth module"],
        "code_review_findings": ["Missing input validation"],
        "engineering_guidance": ["Add integration tests"],
        "recommended_actions": ["Request a second reviewer"],
        "sources_consulted": ["owasp_security"],
    }
    feature_vector = {"ns": 2, "nd": 3, "nf": 5}
    ml_result = {
        "shap_explanation": {
            "top_contributions": [
                {"feature_name": "nf", "feature_value": 5, "shap_value": 0.12, "direction": "increases_risk"},
            ]
        }
    }

    output = _build_check_output(report, feature_vector, ml_result)

    assert "title" in output and "HIGH" in output["title"]
    assert "73%" in output["title"]
    assert "Missing input validation" in output["summary"]
    assert "Request a second reviewer" in output["summary"]
    assert "<details>" in output["text"]
    assert "nf" in output["text"]


def test_build_check_output_handles_empty_lists():
    report = {"deployment_risk": "LOW", "bug_probability": 0.1}
    output = _build_check_output(report, {}, {"shap_explanation": {}})
    assert "(none)" in output["summary"]
