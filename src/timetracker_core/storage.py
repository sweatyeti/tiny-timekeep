"""File-system storage layer for session documents."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from .model import Session, now_utc

_RESERVED_NAMES: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class LoadedDocument:
    file_name: str
    session: Session | None
    error: str | None = None
    session_id: str | None = None


class SessionStore:
    def __init__(self, directory: str | os.PathLike) -> None:
        self._directory = Path(directory)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._lock = threading.RLock()

    @property
    def directory(self) -> Path:
        return self._directory

    @staticmethod
    def sanitize_file_name(name: str) -> str:
        stem = name.strip()
        stem = re.sub(r"\s+", "-", stem)
        stem = _INVALID_CHARS_RE.sub("", stem)
        stem = stem.rstrip(". ")
        if stem.upper() in _RESERVED_NAMES:
            stem += "-session"
        if not stem:
            stem = "session"
        stem = stem[:80]
        stem = stem.rstrip(". ")
        return stem

    @staticmethod
    def is_valid_document_file_name(file_name: str) -> bool:
        if not file_name.endswith(".json"):
            return False
        if "/" in file_name or "\\" in file_name:
            return False
        stem = file_name[: -len(".json")]
        if not stem:
            return False
        if SessionStore.sanitize_file_name(stem) != stem:
            return False
        if stem.upper() in _RESERVED_NAMES:
            return False
        return True

    def document_path(self, file_name: str) -> Path:
        return self._directory / file_name

    def allocate_file_name(self, name: str, taken: set[str] | None = None) -> str:
        stem = self.sanitize_file_name(name)
        candidate = f"{stem}.json"
        existing: set[str] = set()
        try:
            for p in self._directory.iterdir():
                if p.name.endswith(".json") and not p.name.startswith(".tmp-"):
                    existing.add(p.name)
        except OSError:
            pass
        if taken:
            existing.update(taken)
        if candidate not in existing:
            return candidate
        counter = 2
        while True:
            candidate = f"{stem}-{counter}.json"
            if candidate not in existing:
                return candidate
            counter += 1

    def load_all(self) -> list[LoadedDocument]:
        results: list[LoadedDocument] = []
        try:
            files = sorted(self._directory.glob("*.json"), key=lambda p: p.name)
        except OSError:
            return results
        for path in files:
            if path.name.startswith(".tmp-"):
                continue
            file_name = path.name
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                results.append(
                    LoadedDocument(
                        file_name=file_name,
                        session=None,
                        error=f"cannot read document: {exc}",
                        session_id=None,
                    )
                )
                continue
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, ValueError) as exc:
                results.append(
                    LoadedDocument(
                        file_name=file_name,
                        session=None,
                        error=f"document is not valid JSON: {exc}",
                        session_id=None,
                    )
                )
                continue
            session, error = Session.from_document(data, file_name=file_name)
            if session is not None:
                results.append(
                    LoadedDocument(
                        file_name=file_name,
                        session=session,
                        error=None,
                        session_id=session.session_id or None,
                    )
                )
            else:
                recovered_id: str | None = None
                if isinstance(data, dict):
                    sid = data.get("sessionId")
                    if isinstance(sid, str) and sid:
                        recovered_id = sid
                results.append(
                    LoadedDocument(
                        file_name=file_name,
                        session=None,
                        error=error,
                        session_id=recovered_id,
                    )
                )
        return results

    def find(
        self, session_id: str
    ) -> tuple[Session | None, str | None, str | None]:
        if not session_id:
            return None, "session_not_found", None
        for doc in self.load_all():
            if doc.session is not None and doc.session.session_id == session_id:
                return doc.session, None, None
            if doc.session is None and doc.session_id == session_id:
                return None, "session_unreadable", doc.error
        return None, "session_not_found", None

    @staticmethod
    def _is_safe_file_name(file_name: str) -> bool:
        if not file_name:
            return False
        if "/" in file_name or "\\" in file_name:
            return False
        if ".." in file_name:
            return False
        if not file_name.endswith(".json"):
            return False
        return True

    def save(self, session: Session) -> None:
        with self._lock:
            self._cleanup_temp_files()
            if session.file_name is None or not self._is_safe_file_name(
                session.file_name
            ):
                session.file_name = self.allocate_file_name(session.name)
            target = self.document_path(session.file_name)
            doc = session.to_document()
            content = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
            fd, tmp_path = tempfile.mkstemp(
                dir=self._directory, prefix=".tmp-", suffix=".json"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, target)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def _cleanup_temp_files(self) -> None:
        now_ts = now_utc().timestamp()
        try:
            for p in self._directory.iterdir():
                if p.name.startswith(".tmp-"):
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        continue
                    if now_ts - mtime > 60:
                        try:
                            p.unlink()
                        except OSError:
                            pass
        except OSError:
            pass