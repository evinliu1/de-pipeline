import json

import pytest

from de_pipeline.errors import DiagnosisError
from de_pipeline.explain import parse_diagnosis, scrub, scrub_failure
from de_pipeline.models import FailedJob, RunFailure
from de_pipeline.render import render_markdown
from de_pipeline.schema import Diagnosis

LEAK = "gh" + "p_" + "a1B2" * 9


def leaky_failure() -> RunFailure:
    return RunFailure(
        jobs=[FailedJob(name="deploy sup3rs3cretvalue", log="clean", failed_steps=["Deploy"])],
        total_failed_jobs=1,
        branch=f"fix/{LEAK}",
        repo="owner/project",
        url=f"https://github.com/owner/project/actions/runs/1?token={LEAK}",
    )


def clean_diagnosis() -> Diagnosis:
    return Diagnosis.model_validate({
        "summary": "a thing broke", "root_cause": "because", "evidence": [],
        "fix_steps": ["do x"], "confidence": "high",
    })


def test_a_secret_echoed_by_the_model_is_scrubbed() -> None:
    diagnosis = Diagnosis.model_validate({
        "summary": f"auth failed using {LEAK}",
        "root_cause": f"the token {LEAK} expired",
        "evidence": [{"excerpt": f"Authorization: token {LEAK}", "explanation": f"see {LEAK}"}],
        "fix_steps": [f"rotate {LEAK}"],
        "confidence": "high",
    })

    blob = json.dumps(scrub(diagnosis, []).model_dump())

    assert LEAK not in blob


def test_a_secret_in_run_metadata_is_scrubbed() -> None:
    failure = scrub_failure(leaky_failure(), ["sup3rs3cretvalue"])

    assert LEAK not in failure.branch
    assert "sup3rs3cretvalue" not in failure.jobs[0].name


def test_the_markdown_comment_does_not_render_a_secret_from_the_url() -> None:
    failure = scrub_failure(leaky_failure(), [])

    assert LEAK not in render_markdown(clean_diagnosis(), failure.url)


def test_scrubbing_keeps_the_fields_a_reader_needs() -> None:
    failure = scrub_failure(leaky_failure(), [])

    assert failure.repo == "owner/project"
    assert failure.jobs[0].failed_steps == ["Deploy"]
    assert failure.branch.startswith("fix/")


def test_a_schema_error_does_not_echo_the_model_reply() -> None:
    reply = json.dumps({"summary": f"auth failed using {LEAK}", "confidence": "high"})

    with pytest.raises(DiagnosisError) as caught:
        parse_diagnosis(reply)

    assert LEAK not in str(caught.value)
    assert "root_cause" in str(caught.value)
