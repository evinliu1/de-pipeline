from de_pipeline.render import code_block, render_markdown
from de_pipeline.schema import Diagnosis


def diagnosis(**overrides: object) -> Diagnosis:
    values = {
        "summary": "Tests fail",
        "root_cause": "A value changed.",
        "evidence": [{"excerpt": "E   assert 3 == 2", "explanation": "Wrong value."}],
        "fix_steps": ["Change it back."],
        "confidence": "high",
        **overrides,
    }
    return Diagnosis.model_validate(values)


def test_mentions_cannot_notify_anyone() -> None:
    body = render_markdown(diagnosis(summary="@octocat broke the build"))

    assert "@octocat" not in body
    assert "@\u200boctocat" in body


def test_html_is_escaped() -> None:
    body = render_markdown(diagnosis(root_cause="<img src=x onerror=alert(1)>"))

    assert "<img" not in body
    assert "&lt;img" in body


def test_code_fences_grow_to_contain_backticks() -> None:
    assert code_block("a\n```\nb") == "````\na\n```\nb\n````"


def test_the_run_link_is_included() -> None:
    body = render_markdown(diagnosis(), "https://github.com/run/1")

    assert "[View the failed run](https://github.com/run/1)" in body


def test_fix_steps_are_numbered() -> None:
    body = render_markdown(diagnosis(fix_steps=["First.", "Second."]))

    assert "1. First.\n2. Second." in body