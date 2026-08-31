"""Create human-confirmed Candidate Knowledge and immutable Evidence versions."""

from dataclasses import dataclass
from datetime import date, datetime

from job_hunter.application.ports import Clock, IdGenerator, UnitOfWorkFactory
from job_hunter.domain.ids import (
    CandidateProfileId,
    CorrelationId,
    EvidenceItemId,
    EvidenceVersionId,
    RunId,
)
from job_hunter.domain.knowledge import (
    CandidateProfile,
    EvidenceItem,
    EvidenceItemVersion,
    EvidenceSensitivity,
    EvidenceType,
    EvidenceValidity,
)
from job_hunter.errors import DependencyUnavailableError, JobHunterError


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _normalize_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize_text(value) for value in values)


@dataclass(frozen=True, slots=True)
class CreateCandidateProfileCommand:
    target_role_keywords: tuple[str, ...]
    skill_keywords: tuple[str, ...]
    preferred_cities: tuple[str, ...]
    correlation_id: CorrelationId
    run_id: RunId


@dataclass(frozen=True, slots=True)
class CreateCandidateProfileResult:
    profile_id: CandidateProfileId
    target_role_keywords: tuple[str, ...]
    skill_keywords: tuple[str, ...]
    preferred_cities: tuple[str, ...]
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


class CreateCandidateProfile:
    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, command: CreateCandidateProfileCommand) -> CreateCandidateProfileResult:
        try:
            profile = CandidateProfile(
                profile_id=self._id_generator.new_candidate_profile_id(),
                target_role_keywords=_normalize_values(command.target_role_keywords),
                skill_keywords=_normalize_values(command.skill_keywords),
                preferred_cities=_normalize_values(command.preferred_cities),
                created_at=self._clock.now(),
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            unit_of_work = self._unit_of_work_factory()
            try:
                # Profiles are immutable snapshots; selecting the newest snapshot as
                # active preserves the exact facts used by earlier screen results.
                unit_of_work.knowledge.add_profile(profile)
                unit_of_work.commit()
            except JobHunterError:
                unit_of_work.rollback()
                raise
            except Exception:
                unit_of_work.rollback()
                raise DependencyUnavailableError(
                    "candidate profile persistence is unavailable"
                ) from None
            finally:
                unit_of_work.close()
        except JobHunterError:
            raise
        except Exception:
            raise DependencyUnavailableError(
                "candidate profile dependency is unavailable"
            ) from None
        return CreateCandidateProfileResult(
            profile_id=profile.profile_id,
            target_role_keywords=profile.target_role_keywords,
            skill_keywords=profile.skill_keywords,
            preferred_cities=profile.preferred_cities,
            created_at=profile.created_at,
            correlation_id=profile.correlation_id,
            run_id=profile.run_id,
        )


@dataclass(frozen=True, slots=True)
class SaveEvidenceCommand:
    evidence_type: EvidenceType
    canonical_content: str
    occurred_on: date | None
    source: str
    provenance: str
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    correlation_id: CorrelationId
    run_id: RunId
    existing_evidence_id: EvidenceItemId | None = None


@dataclass(frozen=True, slots=True)
class SaveEvidenceResult:
    evidence_id: EvidenceItemId
    evidence_version_id: EvidenceVersionId
    active_version_id: EvidenceVersionId
    version_number: int
    evidence_type: EvidenceType
    canonical_content: str
    occurred_on: date | None
    source: str
    provenance: str
    sensitivity: EvidenceSensitivity
    validity: EvidenceValidity
    created_at: datetime
    correlation_id: CorrelationId
    run_id: RunId


class SaveEvidence:
    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, command: SaveEvidenceCommand) -> SaveEvidenceResult:
        try:
            unit_of_work = self._unit_of_work_factory()
        except JobHunterError:
            raise
        except Exception:
            # No UoW exists yet, so rollback is neither possible nor required.
            raise DependencyUnavailableError("evidence persistence is unavailable") from None
        try:
            existing = (
                unit_of_work.knowledge.get_evidence(command.existing_evidence_id)
                if command.existing_evidence_id is not None
                else None
            )
            evidence_id = (
                existing.evidence_id if existing else self._id_generator.new_evidence_item_id()
            )
            version = EvidenceItemVersion(
                version_id=self._id_generator.new_evidence_version_id(),
                evidence_id=evidence_id,
                version_number=len(existing.version_ids) + 1 if existing else 1,
                evidence_type=command.evidence_type,
                canonical_content=_normalize_text(command.canonical_content),
                occurred_on=command.occurred_on,
                source=_normalize_text(command.source),
                provenance=_normalize_text(command.provenance),
                sensitivity=command.sensitivity,
                validity=command.validity,
                created_at=self._clock.now(),
                correlation_id=command.correlation_id,
                run_id=command.run_id,
            )
            if existing is None:
                item = EvidenceItem.create(version)
                unit_of_work.knowledge.add_evidence(item)
            else:
                item = existing.with_version(version)
                unit_of_work.knowledge.save_evidence(item)
            unit_of_work.knowledge.add_evidence_version(version)
            unit_of_work.commit()
        except JobHunterError:
            unit_of_work.rollback()
            raise
        except Exception:
            unit_of_work.rollback()
            raise DependencyUnavailableError("evidence persistence is unavailable") from None
        finally:
            unit_of_work.close()
        return SaveEvidenceResult(
            evidence_id=item.evidence_id,
            evidence_version_id=version.version_id,
            active_version_id=item.active_version_id,
            version_number=version.version_number,
            evidence_type=version.evidence_type,
            canonical_content=version.canonical_content,
            occurred_on=version.occurred_on,
            source=version.source,
            provenance=version.provenance,
            sensitivity=version.sensitivity,
            validity=version.validity,
            created_at=version.created_at,
            correlation_id=version.correlation_id,
            run_id=version.run_id,
        )
