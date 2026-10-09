from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import uuid

from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vnresearch.analysis.pipeline import analyze
from vnresearch.data.fundamentals import company_universe
from vnresearch.domain.models import AnalysisRequest
from vnresearch.platform.jobs import JobStore
from vnresearch.platform.settings import Settings
from vnresearch.reports.export import export_report


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    settings.prepare()
    store = JobStore(settings.data_dir)
    executor = ThreadPoolExecutor(max_workers=settings.workers)

    @asynccontextmanager
    async def lifespan(app):
        store.reconcile_interrupted()
        yield
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="VN Equity Lab", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.settings = store, settings

    def api_access(x_api_key: str | None = Header(default=None)):
        if settings.api_key and (not x_api_key or not hmac.compare_digest(settings.api_key, x_api_key)):
            raise HTTPException(status_code=401, detail="API key không đúng")

    def checked_job(job_id, token):
        try:
            return store.get(job_id, token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ") from exc

    def run_job(job_id, request, inputs):
        try:
            store.update(job_id, "running", "starting", 5)
            report = analyze(request, inputs, lambda phase, percent: store.update(job_id, "running", phase, percent))
            export_report(report, store.job_dir(job_id))
            store.update(job_id, "completed", "completed", 100)
        except Exception as exc:
            store.update(job_id, "failed", "failed", 0, str(exc))

    @app.get("/api/health")
    def health():
        return {"status": "ok", "schema_version": "1.0.0"}

    @app.get("/api/companies", dependencies=[Depends(api_access)])
    def companies(query: str = "", limit: int = 50):
        frame = company_universe()
        if query:
            frame = frame.loc[frame.ticker.str.contains(query.upper(), regex=False) |
                              frame["Tên Doanh Nghiệp"].str.contains(query, case=False, regex=False)]
        return [{"ticker": row.ticker, "name": row["Tên Doanh Nghiệp"]} for _, row in frame.head(max(1, min(limit, 100))).iterrows()]

    @app.get("/api/capabilities", dependencies=[Depends(api_access)])
    def capabilities():
        return {"llm_configured": bool(os.getenv("LLM_API_KEY") or os.getenv("VNRESEARCH_AI_API_KEY")),
                "jev_configured": bool(os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY"))}

    @app.post("/api/uploads/{kind}", dependencies=[Depends(api_access)])
    async def upload(kind: str, file: UploadFile = File(...)):
        if kind not in {"prices", "macro", "news"} or not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Chỉ nhận CSV prices, macro hoặc news")
        data = await file.read(2 * 1024 * 1024 + 1)
        if not data or len(data) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV phải có nội dung và không vượt 2 MB")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="CSV phải là UTF-8") from exc
        upload_id = uuid.uuid4().hex
        (settings.data_dir / "uploads" / f"{upload_id}-{kind}.csv").write_bytes(data)
        return {"id": upload_id, "kind": kind, "bytes": len(data)}

    @app.post("/api/jobs", status_code=202, dependencies=[Depends(api_access)])
    def submit(request: AnalysisRequest):
        inputs = {}
        for kind, identifier in request.datasets.model_dump().items():
            if identifier:
                path = settings.data_dir / "uploads" / f"{identifier}-{kind}.csv"
                if not path.is_file():
                    raise HTTPException(status_code=400, detail=f"Không tìm thấy CSV {kind}")
                inputs[kind] = path
        job_id, token = store.create(request.model_dump_json())
        executor.submit(run_job, job_id, request, inputs)
        return {"id": job_id, "token": token, "status": "queued"}

    @app.get("/api/jobs/{job_id}", dependencies=[Depends(api_access)])
    def job_status(job_id: str, x_job_token: str | None = Header(default=None)):
        row = checked_job(job_id, x_job_token)
        if row["status"] == "completed":
            row["report"] = json.loads((store.job_dir(job_id) / "report.json").read_text(encoding="utf-8"))
        return row

    @app.get("/api/jobs/{job_id}/files/{filename}", dependencies=[Depends(api_access)])
    def download(job_id: str, filename: str, x_job_token: str | None = Header(default=None)):
        row = checked_job(job_id, x_job_token)
        if filename not in {"report.pdf", "report.json", "manifest.json"} or row["status"] != "completed":
            raise HTTPException(status_code=404, detail="Tệp chưa sẵn sàng")
        return FileResponse(store.job_dir(job_id) / filename, filename=f"{row['request']['ticker']}-{filename}")

    static = Path(__file__).resolve().parents[1] / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def homepage():
        return FileResponse(static / "index.html")

    return app
