"""Versioned HTTP contracts for manual job import."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from job_hunter.application.import_job import ImportJobCommand, ImportJobResult
from job_hunter.domain.ids import CorrelationId, JobId, RunId
from job_hunter.domain.jobs import JobLifecycleStatus
from job_hunter.ingestion.manual import ManualJDInput, ManualURLInput


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ManualJDSourceRequest(_RequestModel):
    source_type: Literal["manual_jd"]
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    city: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ManualURLSourceRequest(_RequestModel):
    source_type: Literal["manual_url"]
    url: HttpUrl
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    city: str = Field(min_length=1)
    content: str = Field(min_length=1)


type ManualSourceRequest = Annotated[
    ManualJDSourceRequest | ManualURLSourceRequest,
    Field(discriminator="source_type"),
]


class ImportJobRequest(_RequestModel):
    correlation_id: str = Field(min_length=1, pattern=r"^\S+$")
    run_id: str = Field(min_length=1, pattern=r"^\S+$")
    existing_job_id: str | None = Field(default=None, min_length=1, pattern=r"^\S+$")
    source: ManualSourceRequest

    def to_command(self) -> ImportJobCommand:
        # This is the single HTTP-to-application translation point. Pydantic values
        # are converted to typed inputs here; API DTOs never enter domain state.
        if isinstance(self.source, ManualJDSourceRequest):
            source_input = ManualJDInput(
                title=self.source.title,
                company=self.source.company,
                city=self.source.city,
                content=self.source.content,
            )
        else:
            source_input = ManualURLInput(
                url=str(self.source.url),
                title=self.source.title,
                company=self.source.company,
                city=self.source.city,
                content=self.source.content,
            )
        return ImportJobCommand(
            source_input=source_input,
            correlation_id=CorrelationId(self.correlation_id),
            run_id=RunId(self.run_id),
            existing_job_id=JobId(self.existing_job_id) if self.existing_job_id else None,
        )


class ImportedSourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["manual_jd", "manual_url"]
    locator: str | None
    captured_at: datetime
    last_verified_at: datetime
    freshness: Literal["fresh", "stale"]


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    job_version_id: str
    active_version_id: str
    source_snapshot_id: str
    version_number: int
    lifecycle_status: Literal["imported"]
    source: ImportedSourceResponse
    correlation_id: str
    run_id: str

    @classmethod
    def from_result(cls, result: ImportJobResult) -> "ImportJobResponse":
        if result.lifecycle_status is not JobLifecycleStatus.IMPORTED:
            raise ValueError("job import must reset lifecycle status to imported")
        return cls(
            job_id=str(result.job_id),
            job_version_id=str(result.job_version_id),
            active_version_id=str(result.active_version_id),
            source_snapshot_id=str(result.source_snapshot_id),
            version_number=result.version_number,
            lifecycle_status="imported",
            source=ImportedSourceResponse(
                kind=result.source_kind.value,
                locator=result.source_locator,
                captured_at=result.captured_at,
                last_verified_at=result.last_verified_at,
                freshness=result.freshness_status.value,
            ),
            correlation_id=str(result.correlation_id),
            run_id=str(result.run_id),
        )
