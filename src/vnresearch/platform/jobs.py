"""SQLite queue, immutable uploads and owner-scoped job capabilities."""
from contextlib import contextmanager
from datetime import timedelta
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import uuid

from vnresearch.domain.models import utcnow


TERMINAL = {"completed", "failed", "interrupted"}
ARTIFACT_NAMES = {"report.pdf", "report.json", "manifest.json"}


class QueueFullError(RuntimeError):
    pass


class IdempotencyConflict(ValueError):
    pass


class UploadError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class StateConflict(RuntimeError):
    pass


class JobStore:
    def __init__(self, root: Path, max_pending: int = 32):
        self.root = root.resolve()
        self.max_pending = max_pending
        for child in ("", "jobs", "uploads"):
            (self.root / child).mkdir(parents=True, exist_ok=True)
        self.database = self.root / "jobs.sqlite3"
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("Phiên bản cơ sở dữ liệu mới hơn ứng dụng")
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, request_json TEXT NOT NULL,
                status TEXT NOT NULL, phase TEXT NOT NULL, percent INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT)""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            additions = {
                "owner": "TEXT NOT NULL DEFAULT 'local'", "idempotency_hash": "TEXT",
                "request_hash": "TEXT", "attempt": "INTEGER NOT NULL DEFAULT 0",
                "worker_id": "TEXT", "error_code": "TEXT", "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
                "artifact_json": "TEXT", "token_version": "INTEGER NOT NULL DEFAULT 0",
                "parent_job_id": "TEXT",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            connection.execute("""UPDATE jobs SET error=?,error_code='LEGACY_FAILURE'
                WHERE status IN ('failed','interrupted') AND error_code IS NULL AND error IS NOT NULL""",
                ("Tác vụ cũ kết thúc trước khi có mã lỗi chuẩn; xem xét trước khi chạy lại.",))
            connection.executescript("""
                CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotency ON jobs(owner,idempotency_hash)
                    WHERE idempotency_hash IS NOT NULL;
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created_at);
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL, status TEXT NOT NULL, phase TEXT NOT NULL,
                    percent INTEGER NOT NULL, occurred_at TEXT NOT NULL, code TEXT);
                CREATE TABLE IF NOT EXISTS attempts (
                    job_id TEXT NOT NULL, attempt INTEGER NOT NULL, worker_id TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                    PRIMARY KEY(job_id,attempt));
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
                    bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'validated');
                CREATE TABLE IF NOT EXISTS job_inputs (
                    job_id TEXT NOT NULL, upload_id TEXT NOT NULL, kind TEXT NOT NULL,
                    PRIMARY KEY(job_id,kind));
            """)
            connection.execute("PRAGMA user_version=2")
        secret_path = self.root / ".token-secret"
        with self.connection() as connection:
            protected_jobs = connection.execute("SELECT id,owner,token_hash FROM jobs WHERE token_version=1").fetchall()
        if protected_jobs and not secret_path.is_file():
            raise RuntimeError("Thiếu khóa capability; phục hồi .token-secret cùng cơ sở dữ liệu")
        try:
            fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
        self._secret = secret_path.read_bytes()
        if len(self._secret) != 32:
            raise RuntimeError("Khóa capability cục bộ không hợp lệ")
        if any(not hmac.compare_digest(row["token_hash"], hashlib.sha256(
                self._token(row["id"], row["owner"]).encode()).hexdigest()) for row in protected_jobs):
            raise RuntimeError("Khóa capability không khớp cơ sở dữ liệu; phục hồi khóa gốc")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _token(self, job_id, owner):
        digest = hmac.new(self._secret, (job_id + ":" + owner).encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    @staticmethod
    def _event(connection, job_id, attempt, status, phase, percent, code=None):
        connection.execute(
            "INSERT INTO job_events(job_id,attempt,status,phase,percent,occurred_at,code) VALUES(?,?,?,?,?,?,?)",
            (job_id, attempt, status, phase, percent, utcnow().isoformat(), code),
        )

    def create(self, request_json: str, owner: str = "local", idempotency_key: str | None = None,
               *, parent_job_id: str | None = None):
        request = json.loads(request_json)
        canonical = json.dumps({"request": request, "parent_job_id": parent_job_id}, sort_keys=True,
                               ensure_ascii=False, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        if idempotency_key is not None and (not idempotency_key or len(idempotency_key) > 200 or not idempotency_key.isascii()):
            raise ValueError("Idempotency-Key không hợp lệ")
        idempotency_hash = hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else None
        job_id, now = uuid.uuid4().hex, utcnow().isoformat()
        token = self._token(job_id, owner)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_hash:
                existing = connection.execute(
                    "SELECT * FROM jobs WHERE owner=? AND idempotency_hash=?", (owner, idempotency_hash)
                ).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise IdempotencyConflict("Idempotency-Key đã dùng cho yêu cầu khác")
                    return existing["id"], self._token(existing["id"], owner)
            count = connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= self.max_pending:
                raise QueueFullError("Hàng đợi đã đủ; thử lại sau")
            inputs = self._resolve_inputs(connection, owner, request.get("datasets", {}))
            self.job_dir(job_id).mkdir()
            connection.execute(
                """INSERT INTO jobs(id,token_hash,request_json,status,phase,percent,created_at,updated_at,
                   owner,idempotency_hash,request_hash,token_version,parent_job_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (job_id, hashlib.sha256(token.encode()).hexdigest(), request_json, "queued", "queued", 0,
                 now, now, owner, idempotency_hash, request_hash, parent_job_id),
            )
            for kind, upload_id in request.get("datasets", {}).items():
                if kind in inputs:
                    connection.execute("INSERT INTO job_inputs VALUES(?,?,?)", (job_id, upload_id, kind))
            self._event(connection, job_id, 0, "queued", "queued", 0)
        return job_id, token

    def job_dir(self, job_id: str) -> Path:
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Mã tác vụ không hợp lệ")
        return self.root / "jobs" / job_id

    def get(self, job_id: str, token: str | None, owner: str | None = None):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            events = connection.execute(
                "SELECT attempt,status,phase,percent,occurred_at,code FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT 100",
                (job_id,),
            ).fetchall() if row else []
        if (row is None or not token or len(token) > 4096 or
                (owner is not None and row["owner"] != owner) or
                not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())):
            raise KeyError("Không tìm thấy tác vụ hoặc token không đúng")
        result = dict(row)
        for key in ("token_hash", "idempotency_hash", "request_hash", "token_version", "worker_id", "owner"):
            result.pop(key, None)
        result["request"] = json.loads(result.pop("request_json"))
        result["artifact_manifest"] = json.loads(result.pop("artifact_json") or "{}")
        result["events"] = [dict(event) for event in reversed(events)]
        result["cancel_requested"] = bool(result["cancel_requested"])
        return result

    def claim_next(self, worker_id: str):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            attempt, now = row["attempt"] + 1, utcnow().isoformat()
            changed = connection.execute(
                """UPDATE jobs SET status='running',phase='starting',percent=5,attempt=?,worker_id=?,
                   updated_at=? WHERE id=? AND status='queued'""", (attempt, worker_id, now, row["id"])
            ).rowcount
            if changed != 1:
                return None
            connection.execute("INSERT INTO attempts VALUES(?,?,?,?,NULL,'running')", (row["id"], attempt, worker_id, now))
            self._event(connection, row["id"], attempt, "running", "starting", 5)
            result = dict(row)
            result.update(attempt=attempt, worker_id=worker_id)
            result["request"] = json.loads(row["request_json"])
            return result

    def update(self, job_id: str, status: str, phase: str, percent: int, error: str | None = None,
               *, worker_id: str | None = None, error_code: str | None = None, artifact_manifest: dict | None = None):
        if status not in {"queued", "running", *TERMINAL} or not 0 <= percent <= 100:
            raise ValueError("Trạng thái/tiến độ không hợp lệ")
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or (worker_id is not None and row["worker_id"] != worker_id):
                raise StateConflict("Tác vụ không thuộc worker")
            if row["status"] in TERMINAL or (row["status"] == "queued" and status == "completed"):
                raise StateConflict("Không thể thay đổi tác vụ đã kết thúc")
            if row["status"] == "running" and status == "queued":
                raise StateConflict("Không tự chạy lại tác vụ đang chạy")
            percent = max(row["percent"], percent) if status == "running" or status in TERMINAL else percent
            connection.execute(
                """UPDATE jobs SET status=?,phase=?,percent=?,updated_at=?,error=?,error_code=?,
                   artifact_json=COALESCE(?,artifact_json) WHERE id=?""",
                (status, phase, percent, utcnow().isoformat(), error, error_code,
                 json.dumps(artifact_manifest, ensure_ascii=False) if artifact_manifest is not None else None, job_id),
            )
            self._event(connection, job_id, row["attempt"], status, phase, percent, error_code)
            if status in TERMINAL:
                connection.execute(
                    "UPDATE attempts SET finished_at=?,status=? WHERE job_id=? AND attempt=?",
                    (utcnow().isoformat(), status, job_id, row["attempt"]),
                )

    def reconcile_interrupted(self, *, include_queued: bool = True):
        statuses = ("queued", "running") if include_queued else ("running",)
        placeholders = ",".join("?" for _ in statuses)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(f"SELECT id,attempt,percent FROM jobs WHERE status IN ({placeholders})", statuses).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE jobs SET status='interrupted',phase='interrupted',error=?,error_code='PROCESS_INTERRUPTED',
                       updated_at=? WHERE id=?""",
                    ("Tiến trình dừng khi tác vụ chưa hoàn tất. Không tự lặp lời gọi AI; xem xét trước khi tạo tác vụ mới.",
                     utcnow().isoformat(), row["id"]),
                )
                connection.execute(
                    "UPDATE attempts SET status='interrupted',finished_at=? WHERE job_id=? AND attempt=?",
                    (utcnow().isoformat(), row["id"], row["attempt"]),
                )
                self._event(connection, row["id"], row["attempt"], "interrupted", "interrupted", row["percent"], "PROCESS_INTERRUPTED")

    def cancel(self, job_id, token, owner):
        self.get(job_id, token, owner)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row["status"] in TERMINAL:
                return
            connection.execute("UPDATE jobs SET cancel_requested=1,updated_at=? WHERE id=?", (utcnow().isoformat(), job_id))
            if row["status"] == "queued":
                connection.execute(
                    "UPDATE jobs SET status='failed',phase='failed',error_code='JOB_CANCELLED',error=? WHERE id=?",
                    ("Tác vụ đã hủy trước khi chạy.", job_id),
                )
                self._event(connection, job_id, row["attempt"], "failed", "failed", row["percent"], "JOB_CANCELLED")

    def cancellation_requested(self, job_id):
        with self.connection() as connection:
            row = connection.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
            return bool(row and row[0])

    def register_upload(self, owner, kind, data: bytes, ttl_hours: int):
        if kind not in {"prices", "macro", "news"} or ttl_hours < 1 or not data:
            raise UploadError("UPLOAD_INVALID", "Dữ liệu nhập không hợp lệ")
        identifier, now = uuid.uuid4().hex, utcnow()
        path = self.root / "uploads" / f"{identifier}-{kind}.csv"
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        digest = hashlib.sha256(data).hexdigest()
        try:
            with self.connection() as connection:
                connection.execute("INSERT INTO uploads VALUES(?,?,?,?,?,?,?,'validated')",
                                   (identifier, owner, kind, len(data), digest, now.isoformat(),
                                    (now + timedelta(hours=ttl_hours)).isoformat()))
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {"id": identifier, "kind": kind, "bytes": len(data), "sha256": digest,
                "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(), "validation_status": "header_validated"}

    def _resolve_inputs(self, connection, owner, datasets, *, allow_expired=False):
        inputs = {}
        for kind, identifier in datasets.items():
            if not identifier:
                continue
            if kind not in {"prices", "macro", "news"}:
                raise UploadError("UPLOAD_KIND", "Loại dữ liệu không hợp lệ")
            row = connection.execute("SELECT * FROM uploads WHERE id=? AND owner=? AND kind=?",
                                     (identifier, owner, kind)).fetchone()
            if row is None:
                raise UploadError("UPLOAD_NOT_FOUND", "Không tìm thấy dữ liệu thuộc người dùng")
            if row["status"] != "validated" or (not allow_expired and row["expires_at"] <= utcnow().isoformat()):
                raise UploadError("UPLOAD_EXPIRED", "Dữ liệu đã hết hạn hoặc bị xóa; nhập lại CSV")
            path = self.root / "uploads" / f"{identifier}-{kind}.csv"
            if (not path.is_file() or path.is_symlink() or
                    hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
                raise UploadError("UPLOAD_INTEGRITY", "Dữ liệu nhập không còn khớp checksum")
            inputs[kind] = path
        return inputs

    def resolve_inputs(self, owner, datasets, *, for_job=None):
        with self.connection() as connection:
            if for_job:
                registered = dict(connection.execute("SELECT kind,upload_id FROM job_inputs WHERE job_id=?", (for_job,)))
                if registered != {kind: identifier for kind, identifier in datasets.items() if identifier}:
                    raise UploadError("UPLOAD_INTEGRITY", "Tham chiếu dữ liệu khác lúc tiếp nhận")
            return self._resolve_inputs(connection, owner, datasets, allow_expired=bool(for_job))

    def delete_upload(self, identifier, owner):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM uploads WHERE id=? AND owner=?", (identifier, owner)).fetchone()
            if row is None:
                raise UploadError("UPLOAD_NOT_FOUND", "Không tìm thấy dữ liệu")
            active = connection.execute(
                """SELECT 1 FROM job_inputs i JOIN jobs j ON j.id=i.job_id
                   WHERE i.upload_id=? AND j.status IN ('queued','running') LIMIT 1""", (identifier,)
            ).fetchone()
            if active:
                raise UploadError("UPLOAD_IN_USE", "Dữ liệu đang được tác vụ sử dụng")
            connection.execute("UPDATE uploads SET status='deleted' WHERE id=?", (identifier,))
            (self.root / "uploads" / f"{identifier}-{row['kind']}.csv").unlink(missing_ok=True)

    def cleanup(self, retention_days):
        now = utcnow()
        cutoff = (now - timedelta(days=retention_days)).isoformat()
        with self.connection() as connection:
            expired = connection.execute("SELECT id,owner FROM uploads WHERE expires_at<=? OR status='deleted'", (now.isoformat(),)).fetchall()
        for row in expired:
            try:
                self.delete_upload(row["id"], row["owner"])
            except UploadError:
                continue
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id,status,attempt,percent FROM jobs WHERE status IN ('completed','failed','interrupted') AND updated_at<?", (cutoff,)
            ).fetchall()
            for row in rows:
                for filename in ARTIFACT_NAMES:
                    (self.job_dir(row["id"]) / filename).unlink(missing_ok=True)
                for staging in self.job_dir(row["id"]).glob(".staging-*"):
                    if staging.is_dir() and not staging.is_symlink() and staging.name[9:].isdigit():
                        for child in staging.iterdir():
                            if child.is_file() or child.is_symlink():
                                child.unlink()
                        staging.rmdir()
                if row["status"] == "completed":
                    connection.execute(
                        """UPDATE jobs SET artifact_json=NULL,status='failed',phase='failed',error_code='ARTIFACT_EXPIRED',
                           error=? WHERE id=?""", ("Hiện vật đã hết thời hạn lưu trữ.", row["id"])
                    )
                    self._event(connection, row["id"], row["attempt"], "failed", "failed", row["percent"], "ARTIFACT_EXPIRED")

    def artifact_unavailable(self, job_id):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT attempt,percent FROM jobs WHERE id=? AND status='completed'", (job_id,)).fetchone()
            if row is None:
                return
            connection.execute(
                """UPDATE jobs SET status='failed',phase='failed',error_code='ARTIFACT_UNAVAILABLE',error=?,updated_at=?
                   WHERE id=? AND status='completed'""",
                ("Hiện vật không còn khớp manifest; cần xem xét phục hồi.", utcnow().isoformat(), job_id),
            )
            self._event(connection, job_id, row["attempt"], "failed", "failed", row["percent"], "ARTIFACT_UNAVAILABLE")

    def readiness(self):
        with self.connection() as connection:
            connection.execute("SELECT 1").fetchone()
            counts = dict(connection.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall())
        return {"queue": counts.get("queued", 0), "running": counts.get("running", 0)}


def atomic_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
