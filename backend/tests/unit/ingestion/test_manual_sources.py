import pytest

from job_hunter.domain.jobs import SourceKind
from job_hunter.errors import InputValidationError
from job_hunter.ingestion.manual import (
    ManualJDInput,
    ManualJDSource,
    ManualURLInput,
    ManualURLSource,
)


def test_manual_jd_source_validates_and_preserves_provenance() -> None:
    captured = ManualJDSource().capture(
        ManualJDInput(
            title="  AI   Agent Engineer ",
            company=" Example AI ",
            city=" Shenzhen ",
            content=" Build reliable agents. ",
        )
    )

    assert captured.source_kind is SourceKind.MANUAL_JD
    assert captured.source_locator is None
    assert captured.raw_title == "AI   Agent Engineer"
    assert captured.raw_description == "Build reliable agents."


def test_manual_url_source_requires_user_content_and_valid_http_url() -> None:
    source = ManualURLSource()

    captured = source.capture(
        ManualURLInput(
            url="https://jobs.example/roles/1",
            title="AI Engineer",
            company="Example AI",
            city="Shenzhen",
            content="Build reliable agents.",
        )
    )

    assert captured.source_kind is SourceKind.MANUAL_URL
    assert captured.source_locator == "https://jobs.example/roles/1"

    with pytest.raises(InputValidationError, match=r"valid HTTP\(S\) URL"):
        source.capture(
            ManualURLInput(
                url="javascript:alert(1)",
                title="AI Engineer",
                company="Example AI",
                city="Shenzhen",
                content="Build reliable agents.",
            )
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.example/roles/1?access_token=do-not-store",
        "https://jobs.example/roles/1#access_token=do-not-store",
        "https://jobs.example/roles/1#/apply?X-Amz-Signature=do-not-store",
    ],
)
def test_manual_url_source_rejects_secret_bearing_locator_parameters(url: str) -> None:
    with pytest.raises(InputValidationError, match="sensitive credential") as raised:
        ManualURLSource().capture(
            ManualURLInput(
                url=url,
                title="AI Engineer",
                company="Example AI",
                city="Shenzhen",
                content="Build reliable agents.",
            )
        )

    assert "do-not-store" not in str(raised.value)


def test_manual_url_source_preserves_non_sensitive_job_identity_parameters() -> None:
    url = "https://jobs.example/roles?job_id=42#requirements"

    captured = ManualURLSource().capture(
        ManualURLInput(
            url=url,
            title="AI Engineer",
            company="Example AI",
            city="Shenzhen",
            content="Build reliable agents.",
        )
    )

    assert captured.source_locator == url


@pytest.mark.parametrize("field", ["title", "company", "city", "content"])
def test_manual_sources_reject_empty_required_fields(field: str) -> None:
    values = {
        "title": "AI Engineer",
        "company": "Example AI",
        "city": "Shenzhen",
        "content": "Build reliable agents.",
    }
    values[field] = "   "

    with pytest.raises(InputValidationError, match=f"{field} is required"):
        ManualJDSource().capture(ManualJDInput(**values))
