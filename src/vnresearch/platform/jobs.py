from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import uuid

from vnresearch.domain.models import utcnow


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / "jobs.sqlite3"
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, request_json TEXT NOT NULL,
                status TEXT NOT NULL, phase TEXT NOT NULL, percent INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT)""")

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

    def create(self, request_json: str):
        job_id, token, now = uuid.uuid4().hex, secrets.token_urlsafe(32), utcnow().isoformat()
        with self.connection() as connection:
            connection.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                               (job_id, hashlib.sha256(token.encode()).hexdigest(), request_json,
                                "queued", "queued", 0, now, now, None))
        self.job_dir(job_id).mkdir(parents=True)
        return job_id, token

    def job_dir(self, job_id: str) -> Path:
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Mã tác vụ không hợp lệ")
        return self.root / "jobs" / job_id

    def get(self, job_id: str, token: str | None):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or not token or not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
            raise KeyError("Không tìm thấy tác vụ hoặc token không đúng")
        result = dict(row)
        result.pop("token_hash")
        result["request"] = json.loads(result.pop("request_json"))
        return result

    def update(self, job_id: str, status: str, phase: str, percent: int, error: str | None = None):
        with self.connection() as connection:
            connection.execute("UPDATE jobs SET status=?,phase=?,percent=?,updated_at=?,error=? WHERE id=?",
                               (status, phase, percent, utcnow().isoformat(), error, job_id))

    def reconcile_interrupted(self):
        with self.connection() as connection:
            connection.execute("UPDATE jobs SET status='interrupted',phase='interrupted',error=?,updated_at=? WHERE status IN ('queued','running')",
                               ("Tiến trình trước dừng khi tác vụ chưa hoàn tất. Tạo tác vụ mới để chạy lại.", utcnow().isoformat()))


def atomic_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8", newline="\n")
    temporary.replace(path)
