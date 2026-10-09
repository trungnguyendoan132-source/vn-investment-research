from contextlib import asynccontextmanager
import csv
import hashlib
import io
import inspect
import json
from pathlib import Path
import uuid

from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from vnresearch.api.admission import AdmissionMiddleware
from vnresearch.analysis.pipeline import analyze
from vnresearch.data.fundamentals import company_universe
from vnresearch.domain.models import AnalysisRequest, Report
from vnresearch.platform.jobs import ARTIFACT_NAMES, IdempotencyConflict, JobStore, QueueFullError, StateConflict, UploadError
from vnresearch.platform.locking import DataDirectoryLock
from vnresearch.platform.providers import effective_provider_config
from vnresearch.platform.runtime import Dispatcher, JobCancelled, progress_callback
from vnresearch.platform.settings import ASSETS, Settings
from vnresearch.reports.export import export_report


CSV_HEADERS = {
    "prices": {"ticker", "date", "open", "high", "low", "close", "volume", "price_unit", "source_url"},
    "macro": {"indicator", "label", "year", "value", "unit", "source_url", "retrieved_at"},
    "news": {"ticker", "title", "text", "url", "published_at"},
}


def fail(status, code, message):
    raise HTTPException(status_code=status, detail=message, headers={"X-Error-Code": code})


def validate_csv_header(kind, data):
    try:
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("NUL in CSV")
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(rows)
        if len(header) != len(set(header)) or len(header) > 64 or not CSV_HEADERS[kind].issubset(header):
            raise ValueError("Invalid headers")
        count = 0
        for row in rows:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError("Inconsistent columns")
            count += 1
        if not count:
            raise ValueError("No rows")
    except (UnicodeDecodeError, ValueError, csv.Error, StopIteration):
        fail(400, "INVALID_CSV", "CSV UTF-8 phải có đúng cột bắt buộc, ít nhất một dòng và số cột nhất quán")


def artifact_metadata(directory):
    result = {}
    for name in ARTIFACT_NAMES:
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing artifact")
        data = path.read_bytes()
        result[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != {"report.json", "report.pdf"}:
        raise ValueError("Invalid artifact manifest")
    for name, expected in manifest["files"].items():
        if result[name] != expected:
            raise ValueError("Artifact checksum mismatch")
    report = Report.model_validate_json((directory / "report.json").read_text(encoding="utf-8"))
    if manifest["ticker"] != report.ticker or manifest["mode"] != report.request.mode.value:
        raise ValueError("Manifest report identity mismatch")
    return result, report


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    settings.prepare()
    instance_lock = DataDirectoryLock(settings.data_dir)
    instance_lock.acquire()
    try:
        store = JobStore(settings.data_dir, max_pending=settings.max_pending)
    finally:
        instance_lock.release()

    def run_job(job, worker_id, stop_event):
        job_id = job["id"]
        try:
            request = AnalysisRequest.model_validate(job["request"])
            inputs = store.resolve_inputs(job["owner"], request.datasets.model_dump(), for_job=job_id)
            progress = progress_callback(store, job_id, worker_id, stop_event)
            progress("starting", 5)
            parameters = inspect.signature(analyze).parameters
            accepts_keywords = any(p.kind == p.VAR_KEYWORD for p in parameters.values())
            configured_paths = {"filing_dir": settings.filing_dir or settings.data_dir / "financial-filings",
                                "dataset_dir": settings.dataset_dir or settings.data_dir / "financial-snapshots"}
            options = {name: path for name, path in configured_paths.items()
                       if name in parameters or accepts_keywords}
            report = analyze(request, inputs, progress, **options)
            Report.model_validate(report.model_dump(mode="json"))
            progress("report", 95)
            directory = store.job_dir(job_id)
            staging = directory / f".staging-{job['attempt']}"
            staging.mkdir(exist_ok=False)
            export_report(report, staging)
            metadata, parsed = artifact_metadata(staging)
            if parsed.ticker != request.ticker or parsed.request != request:
                raise ValueError("Report request mismatch")
            if store.cancellation_requested(job_id) or stop_event.is_set():
                raise JobCancelled("Stopped before publication")
            for name in ARTIFACT_NAMES:
                (staging / name).replace(directory / name)
            staging.rmdir()
            store.update(job_id, "completed", "completed", 100, worker_id=worker_id, artifact_manifest=metadata)
        except Exception as exc:
            if isinstance(exc, StateConflict):
                return
            if isinstance(exc, JobCancelled):
                status = "interrupted" if stop_event.is_set() else "failed"
                code = "PROCESS_INTERRUPTED" if stop_event.is_set() else "JOB_CANCELLED"
                message = "Tác vụ dừng tại ranh giới giai đoạn. Không tự lặp lời gọi AI."
            elif isinstance(exc, UploadError):
                status, code, message = "failed", exc.code, str(exc)
            else:
                status, code = "failed", "PIPELINE_FAILED"
                message = "Không hoàn tất được tác vụ; kiểm tra cấu hình/dữ liệu và sự kiện giai đoạn trước khi chạy lại."
            try:
                store.update(job_id, status, status, 0, message, worker_id=worker_id, error_code=code)
            except StateConflict:
                pass

    dispatcher = Dispatcher(store, settings.workers, run_job,
                            maintenance=lambda: store.cleanup(settings.retention_days))

    @asynccontextmanager
    async def lifespan(app):
        instance_lock.acquire()
        try:
            store.reconcile_interrupted(include_queued=False)
            store.cleanup(settings.retention_days)
            dispatcher.start()
            yield
        finally:
            if dispatcher.close():
                instance_lock.release()
            else:
                raise RuntimeError("Worker chưa dừng; giữ khóa instance để tránh chạy trùng")

    app = FastAPI(title="VN Equity Lab", version="0.2.0", lifespan=lifespan)
    app.state.store, app.state.settings = store, settings
    app.state.dispatcher, app.state.instance_lock = dispatcher, instance_lock
    app.add_middleware(AdmissionMiddleware, settings=settings)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse({"detail": exc.detail, "code": (exc.headers or {}).get("X-Error-Code", "HTTP_ERROR"),
                             "request_id": getattr(request.state, "request_id", None)},
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        errors = [{"location": list(error["loc"]), "type": error["type"]} for error in exc.errors()]
        return JSONResponse({"detail": "Yêu cầu không đúng contract; kiểm tra trường được chỉ rõ.",
                             "code": "INVALID_REQUEST", "errors": errors,
                             "request_id": getattr(request.state, "request_id", None)}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse({"detail": "Lỗi dịch vụ; dùng request_id để đối chiếu.",
                             "code": "SERVER_ERROR", "request_id": request_id}, status_code=500,
                            headers={"X-Request-ID": request_id or uuid.uuid4().hex,
                                     "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    def api_access(request: Request, x_api_key: str | None = Header(default=None)):
        return request.state.principal

    def checked_job(job_id, token, owner):
        try:
            return store.get(job_id, token, owner)
        except (KeyError, ValueError):
            fail(404, "JOB_NOT_FOUND", "Không tìm thấy tác vụ")

    def checked_artifacts(job_id, row):
        try:
            metadata, report = artifact_metadata(store.job_dir(job_id))
            if row["artifact_manifest"] and metadata != row["artifact_manifest"]:
                raise ValueError("Artifact changed after publication")
            return report
        except (OSError, ValueError, KeyError, TypeError):
            store.artifact_unavailable(job_id)
            return None

    @app.get("/api/health")
    @app.get("/api/health/live")
    def health():
        return {"status": "ok", "schema_version": "1.1.0"}

    @app.get("/api/health/ready")
    def readiness():
        checks = {}
        try:
            checks["database"] = store.readiness()
        except Exception:
            checks["database"] = False
        try:
            probe = settings.data_dir / (".ready-" + uuid.uuid4().hex)
            with probe.open("xb") as handle:
                handle.write(b"1")
            probe.unlink()
            checks["data_directory"] = True
        except OSError:
            checks["data_directory"] = False
        try:
            manifest = json.loads((ASSETS / "snapshot_manifest.json").read_text(encoding="utf-8"))
            paths = [ASSETS / "companies.csv", ASSETS / "fonts/DejaVuSans.ttf"]
            paths += [ASSETS / "bctc" / "/".join(item["file"].split("/")[-2:]) for item in manifest["data"]]
            checks["assets"] = bool(paths) and all(path.is_file() and path.stat().st_size > 0 for path in paths)
        except (OSError, ValueError, KeyError, TypeError):
            checks["assets"] = False
        checks["dispatcher"] = dispatcher.ready
        ready = all(value is not False for value in checks.values())
        return JSONResponse({"status": "ready" if ready else "unavailable", "checks": checks},
                            status_code=200 if ready else 503)

    @app.get("/api/companies")
    def companies(query: str = "", limit: int = 50, owner=Depends(api_access)):
        frame = company_universe()
        if query:
            frame = frame.loc[frame.ticker.str.contains(query.upper(), regex=False) |
                              frame["Tên Doanh Nghiệp"].str.contains(query, case=False, regex=False)]
        return [{"ticker": row.ticker, "name": row["Tên Doanh Nghiệp"]} for _, row in frame.head(max(1, min(limit, 100))).iterrows()]

    @app.get("/api/capabilities")
    def capabilities(owner=Depends(api_access)):
        result = {}
        for kind in ("llm", "jev"):
            try:
                config = effective_provider_config(kind)
                result[kind + "_configured"] = config.configured
                result[kind + "_configuration_status"] = "configured_unverified" if config.configured else "missing_key"
                result[kind + "_model"] = config.model
            except ValueError:
                result[kind + "_configured"] = False
                result[kind + "_configuration_status"] = "invalid_configuration"
        return result

    @app.post("/api/uploads/{kind}", openapi_extra={"requestBody": {"required": True, "content": {
        "multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {
            "file": {"type": "string", "format": "binary"}}}}}}})
    async def upload(kind: str, request: Request, owner=Depends(api_access)):
        if kind not in CSV_HEADERS:
            fail(400, "INVALID_UPLOAD_KIND", "Chỉ nhận CSV prices, macro hoặc news")
        async with request.form(max_files=1, max_fields=0) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile) or not (file.filename or "").lower().endswith(".csv"):
                fail(400, "INVALID_UPLOAD_KIND", "Chỉ nhận một tệp CSV trong trường file")
            data = await file.read(settings.upload_max_bytes + 1)
        if not data or len(data) > settings.upload_max_bytes:
            fail(413, "UPLOAD_TOO_LARGE", "CSV phải có nội dung và không vượt 2 MB")
        validate_csv_header(kind, data)
        return store.register_upload(owner, kind, data, settings.upload_ttl_hours)

    @app.delete("/api/uploads/{identifier}")
    def delete_upload(identifier: str, owner=Depends(api_access)):
        try:
            store.delete_upload(identifier, owner)
        except UploadError as exc:
            fail(409 if exc.code == "UPLOAD_IN_USE" else 404, exc.code, str(exc))
        return {"status": "deleted"}

    def accept(request, owner, idempotency_key, parent_job_id=None):
        try:
            job_id, token = store.create(request.model_dump_json(), owner, idempotency_key, parent_job_id=parent_job_id)
        except QueueFullError:
            raise HTTPException(status_code=429, detail="Hàng đợi đã đủ; thử lại sau",
                                headers={"Retry-After": "2", "X-Error-Code": "QUEUE_FULL"}) from None
        except IdempotencyConflict as exc:
            fail(409, "IDEMPOTENCY_CONFLICT", str(exc))
        except UploadError as exc:
            fail(410 if exc.code == "UPLOAD_EXPIRED" else 400, exc.code, str(exc))
        except ValueError:
            fail(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key không hợp lệ")
        row = store.get(job_id, token, owner)
        return {"id": job_id, "token": token, "status": row["status"]}

    @app.post("/api/jobs", status_code=202)
    def submit(request: AnalysisRequest, owner=Depends(api_access),
               idempotency_key: str | None = Header(default=None)):
        return accept(request, owner, idempotency_key)

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, x_job_token: str | None = Header(default=None), owner=Depends(api_access)):
        row = checked_job(job_id, x_job_token, owner)
        if row["status"] == "completed":
            report = checked_artifacts(job_id, row)
            if report is None:
                row = checked_job(job_id, x_job_token, owner)
            else:
                row["report"] = report.model_dump(mode="json")
        return row

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, x_job_token: str | None = Header(default=None), owner=Depends(api_access)):
        checked_job(job_id, x_job_token, owner)
        store.cancel(job_id, x_job_token, owner)
        return store.get(job_id, x_job_token, owner)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, x_job_token: str | None = Header(default=None), owner=Depends(api_access),
                  idempotency_key: str | None = Header(default=None)):
        row = checked_job(job_id, x_job_token, owner)
        if row["status"] not in {"failed", "interrupted"}:
            fail(409, "JOB_NOT_RETRYABLE", "Chỉ chạy lại tác vụ thất bại hoặc bị gián đoạn")
        return accept(AnalysisRequest.model_validate(row["request"]), owner, idempotency_key, job_id)

    @app.get("/api/jobs/{job_id}/files/{filename}")
    def download(job_id: str, filename: str, x_job_token: str | None = Header(default=None), owner=Depends(api_access)):
        row = checked_job(job_id, x_job_token, owner)
        if filename not in ARTIFACT_NAMES:
            fail(404, "FILE_NOT_FOUND", "Tệp không hợp lệ")
        if row["error_code"] in {"ARTIFACT_UNAVAILABLE", "ARTIFACT_EXPIRED"}:
            fail(410 if row["error_code"] == "ARTIFACT_EXPIRED" else 409, row["error_code"], row["error"])
        if row["status"] != "completed":
            fail(404, "FILE_NOT_READY", "Tệp chưa sẵn sàng")
        if checked_artifacts(job_id, row) is None:
            fail(409, "ARTIFACT_UNAVAILABLE", "Hiện vật không còn khớp manifest")
        return FileResponse(store.job_dir(job_id) / filename, filename=f"{row['request']['ticker']}-{filename}")

    static = Path(__file__).resolve().parents[1] / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def homepage():
        return FileResponse(static / "index.html")

    return app
