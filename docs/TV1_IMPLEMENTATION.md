# TV1: platform implementation and local verification

Implemented on `member01-platform` in `src/vnresearch/api/`, `platform/`, and `domain/`.
This record covers platform behavior. Financial accuracy, live provider quality, and the
other five members' acceptance requirements still need their own evidence.

## API and ownership

- A request containing only a ticker defaults to `mode=live`, `use_ai=true`, and
  `use_jev=true`. Configured providers participate automatically; callers can explicitly
  set either flag to false. `mode=demo` disables omitted provider flags to keep the
  offline demo offline; explicitly enabled demo flags are preserved for deliberate tests.
- `VNRESEARCH_USER_TOKENS_JSON` maps stable user names to separate API tokens.
  `X-API-Key` identifies an owner; a job also requires its `X-Job-Token`.
  An owner's token cannot read another owner's job or reuse another owner's upload.
- The legacy `VNRESEARCH_API_KEY` identifies the shared `local` owner. Without any
  configured access token, business endpoints permit loopback clients only. Public
  health endpoints remain available without a token.
- Authentication runs before body ingestion or multipart parsing. Duplicate authentication,
  job-token, idempotency, and content-length headers are rejected. API bodies are bounded
  even without `Content-Length`: 128 KiB for ordinary requests and the upload limit plus
  64 KiB of multipart overhead for upload requests.
- CSV uploads require UTF-8, the required header, unique column names, consistent row
  widths, and at least one data row. `validation_status=header_validated` reports exactly
  that check; it does not claim that financial data has been verified against its source.
- Uploads have owner, kind, SHA-256, byte count, creation time, and expiry metadata.
  Job admission checks all of these references and the file hash. An upload cannot be
  deleted while queued/running work references it. Accepted jobs can still read their
  pinned input after its admission expiry, while new jobs must supply a valid upload.
- API responses include `X-Request-ID`, `Cache-Control: no-store`, and
  `X-Content-Type-Options: nosniff`. Errors return a stable `code` and `request_id`.
  Validation responses identify fields/types without echoing submitted values. Unexpected
  errors and pipeline failures use controlled messages; migrated legacy raw errors are
  replaced with `LEGACY_FAILURE` messages.

## Durable queue and recovery

- SQLite schema version 2 adds owner, idempotency, attempt, worker, cancellation, and
  artifact fields to the previous jobs table. Existing job IDs and token hashes remain
  readable. Uploads, accepted inputs, attempts, and stage events have separate tables.
- `BEGIN IMMEDIATE` serializes queue admission, claims, and transitions. `max_pending`
  limits the total queued/running work. A fixed pool of one to four workers polls the
  persisted queue; it does not allocate a background thread for each submission.
- `Idempotency-Key` is scoped to the owner and canonical request, including the parent
  job on an explicit retry. Matching repeats return the same job and token even when the
  queue is full. A changed request returns 409; queue capacity returns 429/`QUEUE_FULL`
  with `Retry-After`.
- An operating-system lock protects store initialization and the active application
  instance for the same data directory. A second instance cannot migrate or reconcile
  a live instance's ledger. The lock is released by the OS after process death.
- Startup changes only previously running jobs to `interrupted`; queued jobs continue
  through the new dispatcher. Running attempts are never replayed automatically because
  a provider call may already have produced an external effect before process death.
- Cancellation is cooperative at stage/publication boundaries. It cannot forcibly stop
  a provider request already executing. Queued cancellations finish without running.
  `/api/jobs/{id}/retry` is an explicit operation for failed/interrupted work and creates
  a new UUID/token linked by `parent_job_id`. Stage failures preserve achieved progress.
- The local `.token-secret` must be backed up with `jobs.sqlite3` and its WAL state.
  Missing or mismatched secret material blocks startup rather than silently rotating
  capabilities and breaking idempotent replay. Restore the original secret and ledger
  together; do not overwrite the secret with a newly generated key.

## Artifacts, retention, and readiness

- Reports are exported into a per-attempt staging directory. Before publication the
  app validates the report schema/request, manifest identity, exact file set, bytes,
  and SHA-256. `completed` is written only after all three files have been published.
- Status and download requests revalidate report/manifest hashes against the ledger.
  Corruption/missing files change the visible state to `ARTIFACT_UNAVAILABLE`, append
  an event, and block download. Retention expiry returns 410/`ARTIFACT_EXPIRED`.
- Cleanup runs at startup and every 60 seconds on a separate maintenance thread.
  It removes unused expired uploads and expired artifacts/staging files. It preserves
  the original failure/interruption code when a failed job has no retained artifact.
  Job, input-reference, attempt, and event metadata remain in SQLite for audit history;
  the implementation does not claim to delete that ledger under the artifact policy.
- Liveness reports the process endpoint. Readiness additionally checks database access,
  a real data-directory write/delete probe, required packaged asset presence, worker
  and maintenance thread health. Asset presence is not a financial provenance check.
- Shutdown requests worker/maintenance termination and joins for up to 30 seconds.
  If a worker is still executing, the application keeps its instance lock and raises
  instead of allowing a second dispatcher to run against the same directory.

## Provider and report contracts

- `platform/providers.py` provides the effective LLM/Jev endpoint and model configuration.
  HTTPS is allowed; plaintext HTTP is restricted to literal loopback or `localhost`
  resolving exclusively to loopback. Credentials, query, fragment, malformed port,
  and non-loopback HTTP are rejected. LLM base URLs and Jev's native `/v1/systemone`
  endpoint are normalized separately. Callers must disable redirects.
- Provider keys and user tokens are excluded from configuration `repr`. Configuration
  presence is reported as `configured_unverified`; it does not establish valid live
  credentials, model compatibility, or source support.
- Report schema 1.1.0 adds optional publication, period, basis, unit, currency, mapping,
  dataset, and verification metadata. Defaults remain `unknown`, not `verified`.
  Reports marked 1.0.0 remain readable; unknown schema versions are rejected.
- Validation rejects non-finite financial values, timezone-free source timestamps,
  impossible period ordering, invalid source URLs/IDs, duplicate years/source IDs,
  ticker mismatches, and unresolved section/metric/news/fact-metadata/AI source links.
  Source-link validity does not prove the content of an AI claim is supported.

## Verification evidence

The platform/provider tests use local files, SQLite, HTTP TestClient, and explicit mock
provider fixtures. They make no paid model calls. The crash test starts a separate OS
process running the actual app/dispatcher, leaves one request inside a simulated LLM
stage, queues another, terminates the process, and restarts the app. It verifies that
the interrupted request still has exactly one attempt and only the queued request is
executed after restart. This validates local recovery behavior, not live AI quality.

Additional regressions cover concurrent claims/capacity, idempotency and conflicts,
owner separation, body limits before multipart spooling, remote unauthenticated access,
sanitized errors/headers, old-table migration, capability-secret restoration, explicit
retry, upload lifetime/pinning, artifact corruption, retention while the app stays up,
and readiness degradation. Existing report tests also parse real PDF text and reconcile
PDF/JSON hashes. PDF rendering code was not changed by this platform work.

Run from the repository root:

```powershell
..\audit-venv\Scripts\python.exe -m pytest -q
..\audit-venv\Scripts\python.exe -m ruff check src tests
git diff --check
```

Local validation on 2026-10-09: **69 tests passed in 10.64 seconds**, ruff passed,
and `git diff --check` passed. Git's CRLF-to-LF notices are line-ending notices.
Clean-wheel packaging and CI configuration are handled by the integration owner. A
workflow template is not a successful GitHub Actions run; no live CI result is claimed
by this record.
