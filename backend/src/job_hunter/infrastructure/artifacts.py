"""Private local content-addressed storage for redacted derivative context."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path

from job_hunter.domain.ids import ArtifactId
from job_hunter.domain.runtime_context import ArtifactRecord
from job_hunter.errors import DependencyUnavailableError


def _verify(record: ArtifactRecord, content: str) -> None:
    encoded = content.encode()
    if (
        hashlib.sha256(encoded).hexdigest() != record.content_hash
        or len(encoded) != record.byte_size
        or ArtifactId.from_content_hash(record.content_hash) != record.artifact_id
    ):
        raise DependencyUnavailableError("runtime artifact is invalid")


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._content: dict[ArtifactId, str] = {}

    def write(self, record: ArtifactRecord, content: str) -> None:
        _verify(record, content)
        existing = self._content.get(record.artifact_id)
        if existing is not None and existing != content:
            raise DependencyUnavailableError("runtime artifact is invalid")
        self._content[record.artifact_id] = content

    def read(self, record: ArtifactRecord) -> str:
        try:
            content = self._content[record.artifact_id]
        except KeyError:
            raise DependencyUnavailableError("runtime artifact is unavailable") from None
        _verify(record, content)
        return content


class LocalArtifactStore:
    """Stores only typed content IDs; callers cannot supply paths."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, artifact_id: ArtifactId) -> Path:
        return self._root / str(artifact_id)

    def _ensure_private_root(self) -> None:
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = self._root.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise DependencyUnavailableError("runtime artifact is unavailable")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            os.chmod(self._root, 0o700, follow_symlinks=False)
        if stat.S_IMODE(self._root.lstat().st_mode) != 0o700:
            raise DependencyUnavailableError("runtime artifact is unavailable")

    @staticmethod
    def _ensure_private_file(path: Path) -> None:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise DependencyUnavailableError("runtime artifact is unavailable")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            os.chmod(path, 0o600, follow_symlinks=False)
        if stat.S_IMODE(path.lstat().st_mode) != 0o600:
            raise DependencyUnavailableError("runtime artifact is unavailable")

    def _sync_root(self) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(self._root, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def write(self, record: ArtifactRecord, content: str) -> None:
        _verify(record, content)
        try:
            self._ensure_private_root()
            path = self._path(record.artifact_id)
            try:
                path.lstat()
            except FileNotFoundError:
                pass
            else:
                self._ensure_private_file(path)
                existing = path.read_text(encoding="utf-8")
                _verify(record, existing)
                return
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self._root,
                prefix=f".{record.artifact_id}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            try:
                try:
                    handle = os.fdopen(descriptor, "w", encoding="utf-8")
                except Exception:
                    os.close(descriptor)
                    raise
                with handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
                self._ensure_private_file(path)
                self._sync_root()
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        except DependencyUnavailableError:
            raise
        except Exception:
            raise DependencyUnavailableError("runtime artifact is unavailable") from None

    def read(self, record: ArtifactRecord) -> str:
        try:
            self._ensure_private_root()
            path = self._path(record.artifact_id)
            self._ensure_private_file(path)
            content = path.read_text(encoding="utf-8")
        except DependencyUnavailableError:
            raise
        except Exception:
            raise DependencyUnavailableError("runtime artifact is unavailable") from None
        _verify(record, content)
        return content
