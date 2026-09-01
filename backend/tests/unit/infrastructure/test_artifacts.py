import hashlib
import os
from pathlib import Path

import pytest

from job_hunter.domain.ids import ArtifactId
from job_hunter.domain.retrieval import estimate_tokens
from job_hunter.domain.runtime_context import ARTIFACT_POLICY_VERSION, ArtifactRecord
from job_hunter.errors import DependencyUnavailableError
from job_hunter.infrastructure.artifacts import LocalArtifactStore


def _record(content: str) -> ArtifactRecord:
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return ArtifactRecord(
        artifact_id=ArtifactId.from_content_hash(content_hash),
        content_hash=content_hash,
        byte_size=len(content.encode()),
        estimated_tokens=estimate_tokens(content),
        policy_version=ARTIFACT_POLICY_VERSION,
    )


def test_local_artifact_is_content_addressed_private_and_reopens(tmp_path: Path) -> None:
    content = "redacted synthetic candidate evidence"
    record = _record(content)
    root = tmp_path / "artifacts"

    LocalArtifactStore(root).write(record, content)
    reopened = LocalArtifactStore(root)

    assert reopened.read(record) == content
    assert (root.stat().st_mode & 0o777) == 0o700
    assert ((root / str(record.artifact_id)).stat().st_mode & 0o777) == 0o600


def test_local_artifact_corruption_fails_closed_without_content_or_path(
    tmp_path: Path,
) -> None:
    content = "redacted synthetic candidate evidence"
    record = _record(content)
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root)
    store.write(record, content)
    (root / str(record.artifact_id)).write_text("fabricated private fact", encoding="utf-8")

    with pytest.raises(DependencyUnavailableError) as captured:
        store.read(record)

    message = str(captured.value)
    assert message == "runtime artifact is invalid"
    assert content not in message
    assert str(root) not in message


def test_crash_leftover_temporary_file_does_not_block_atomic_publish(tmp_path: Path) -> None:
    content = "redacted synthetic candidate evidence"
    record = _record(content)
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / f"{record.artifact_id}.tmp").write_text("crash residue", encoding="utf-8")

    store = LocalArtifactStore(root)
    store.write(record, content)

    assert store.read(record) == content


def test_existing_root_and_artifact_permissions_are_tightened(tmp_path: Path) -> None:
    content = "redacted synthetic candidate evidence"
    record = _record(content)
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o755)
    store = LocalArtifactStore(root)
    store.write(record, content)
    path = root / str(record.artifact_id)
    os.chmod(root, 0o755)
    os.chmod(path, 0o644)

    assert store.read(record) == content
    assert (root.stat().st_mode & 0o777) == 0o700
    assert (path.stat().st_mode & 0o777) == 0o600


def test_symlink_artifact_root_fails_closed_without_path_disclosure(tmp_path: Path) -> None:
    content = "redacted synthetic candidate evidence"
    record = _record(content)
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "artifacts"
    root.symlink_to(target, target_is_directory=True)

    with pytest.raises(DependencyUnavailableError) as captured:
        LocalArtifactStore(root).write(record, content)

    assert str(captured.value) == "runtime artifact is unavailable"
    assert str(root) not in str(captured.value)


def test_failed_atomic_publish_cleans_only_owned_unique_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = "redacted synthetic candidate evidence"
    record = _record(content)
    root = tmp_path / "artifacts"

    def _fail_replace(source: str | Path, destination: str | Path) -> None:
        del source, destination
        raise OSError("synthetic publish failure")

    monkeypatch.setattr(os, "replace", _fail_replace)
    with pytest.raises(DependencyUnavailableError, match="runtime artifact is unavailable"):
        LocalArtifactStore(root).write(record, content)

    assert tuple(root.iterdir()) == ()
