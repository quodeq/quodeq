"""Publish a run's event log and evidence without restoring its local archive.

Publishing copies a finished run into the shared clone. When the local run is
archived, its logs come straight out of ``archive.tar.gz``: either repacked
into a new archive without ``evaluation.db`` (the shared archive form) or
extracted beside a run the shared repository already holds in full form.
Nothing in the local run folder is restored, stamped or rewritten, and the
run lock is held while the archive is read so a concurrent restore or archive
cannot change it underneath.

A written archive is deterministic: members in a fixed order with their
source modification times, gzip header time 0. Republishing an unchanged run
writes the same bytes, and a file whose bytes did not change is left in place.
"""
from __future__ import annotations

import filecmp
import gzip
import io
import os
import tarfile
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from quodeq.data.fs.run_archive import READ_ERRORS, check_members
from quodeq.data.fs.run_archive_files import EVENTS_NAME, archive_sources, is_plain_file
from quodeq.data.fs.run_archive_guard import LOCK_NAME, run_lock_if_writable
from quodeq.data.fs.run_archive_limits import RunArchiveError, check_restore_dirs, read_members
from quodeq.data.fs.run_archive_wal import DB_NAME

_FILE_MODE = 0o644
_READ_GZ = "r:gz"  # tarfile mode: read a gzipped archive


@contextmanager
def _run_read_lock(run_dir: Path) -> Iterator[None]:
    """The run lock when the run was ever archived (it then has a lock file); no new lock file otherwise."""
    if not (run_dir / LOCK_NAME).exists():
        yield
        return
    with run_lock_if_writable(run_dir):
        yield


def _order(name: str) -> tuple[bool, str]:
    return name != EVENTS_NAME, name


def _log_members(tar: tarfile.TarFile, dest_dir: Path) -> list[tarfile.TarInfo]:
    """The archive's log members in archive order, after every safety check; never the database."""
    members = read_members(tar)
    check_members(members, dest_dir)
    return sorted((m for m in members if m.name != DB_NAME), key=lambda m: _order(m.name))


def _tar_info(name: str, size: int, mtime: float) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = size, int(mtime), _FILE_MODE
    return info


def _replace_if_changed(tmp: Path, dest: Path) -> None:
    """Move *tmp* over *dest*, or drop it when *dest* already holds the same bytes."""
    if is_plain_file(dest) and filecmp.cmp(tmp, dest, shallow=False):
        tmp.unlink()
        return
    os.replace(tmp, dest)


def _write_beside(dest: Path, fill: Callable[[object], None]) -> Path:
    """Write *dest* through a temporary file in its folder; *fill* gets the open binary stream."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as raw:
            fill(raw)
            raw.flush()
            os.fsync(raw.fileno())
        _replace_if_changed(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest


def _write_tar(dest_archive: Path, add: Callable[[tarfile.TarFile], None]) -> Path:
    def fill(raw) -> None:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
                add(tar)

    return _write_beside(dest_archive, fill)


def _check_destination(dest_dir: Path) -> None:
    if dest_dir.exists():
        check_restore_dirs(dest_dir)


def repack_without_db(archive: Path, dest_archive: Path) -> Path:
    """Write *dest_archive* holding *archive*'s event log and evidence only; its path.

    Raises ``RunArchiveError`` when *archive* is unsafe, over the limits or
    unreadable; *archive* itself is never changed.
    """
    _check_destination(dest_archive.parent)
    with _run_read_lock(archive.parent):
        try:
            with tarfile.open(archive, _READ_GZ) as src:
                members = _log_members(src, dest_archive.parent)

                def add(tar: tarfile.TarFile) -> None:
                    for member in members:
                        tar.addfile(_tar_info(member.name, member.size, member.mtime), src.extractfile(member))

                return _write_tar(dest_archive, add)
        except READ_ERRORS as exc:
            raise RunArchiveError(f"cannot read run archive {archive}: {exc}") from exc


def pack_run_logs(run_dir: Path, dest_archive: Path) -> Path:
    """Write *dest_archive* from a live run's event log and evidence, the same bytes a repack of its archive gives."""
    _check_destination(dest_archive.parent)
    with _run_read_lock(run_dir):
        sources = sorted(((n, p) for n, p in archive_sources(run_dir) if n != DB_NAME), key=lambda s: _order(s[0]))

        def add(tar: tarfile.TarFile) -> None:
            for name, path in sources:
                with open(path, "rb") as fh:
                    stat = os.fstat(fh.fileno())
                    tar.addfile(_tar_info(name, stat.st_size, stat.st_mtime), fh)

        return _write_tar(dest_archive, add)


def rewrite_archive_logs(archive: Path, transform: Callable[[str, bytes], bytes]) -> Path:
    """Rewrite a published *archive* with each log member's bytes passed through *transform*; its path.

    *transform* gets the member name and its bytes. The result is as
    deterministic as any archive written here (same order, same mtimes), so an
    unchanged run republished rewrites nothing. Raises ``RunArchiveError`` when
    *archive* is unsafe, over the limits or unreadable.
    """
    try:
        with tarfile.open(archive, _READ_GZ) as src:
            members = _log_members(src, archive.parent)
            rewritten = [(m, transform(m.name, src.extractfile(m).read())) for m in members]
    except READ_ERRORS as exc:
        raise RunArchiveError(f"cannot read run archive {archive}: {exc}") from exc

    def add(tar: tarfile.TarFile) -> None:
        for member, data in rewritten:
            tar.addfile(_tar_info(member.name, len(data), member.mtime), io.BytesIO(data))

    return _write_tar(archive, add)


def extract_members_to(archive: Path, dest_dir: Path, names: list[str] | None = None) -> list[Path]:
    """Extract *archive*'s log members (or only *names*) into *dest_dir*; the paths written.

    Every member is checked before anything is written; the database is never
    extracted. Raises ``RunArchiveError`` on an unsafe or unreadable archive.
    """
    _check_destination(dest_dir)
    written: list[Path] = []
    with _run_read_lock(archive.parent):
        try:
            with tarfile.open(archive, _READ_GZ) as src:
                members = [m for m in _log_members(src, dest_dir) if names is None or m.name in names]
                for member in members:
                    stream = src.extractfile(member)
                    written.append(_write_beside(dest_dir / member.name, lambda raw, s=stream: _copy_stream(s, raw)))
        except READ_ERRORS as exc:
            raise RunArchiveError(f"cannot read run archive {archive}: {exc}") from exc
    return written


def _copy_stream(src, dest) -> None:
    for chunk in iter(lambda: src.read(1 << 20), b""):
        dest.write(chunk)
