# TV2: data implementation and evidence

TV2 provides automatic retrieval for curated original filings, an explicit daily market provider, immutable input releases, exact financial mappings, and data-quality results. A successful HTTP response or passing regression test does not certify market-wide financial correctness. Report orchestration and suppression of unverified observations belong to the integrated analysis pipeline.

## Verified scope and remaining coverage

The packaged [selected filing envelopes](../examples/verified-filings/README.md) contain **51 visually checked source observations in seven envelopes**: FPT, SSI and VCB audited consolidated annual 2025 statements, plus four 2024 comparative observations per issuer. Each annual current-year envelope includes 11 facts. A separate SSI reviewed consolidated H1 2026 envelope includes six selected facts, published on 2026-08-14; interim figures are not doubled or mixed with annual ratios. The originals were scanned PDFs, so the recorded snippets and numbers were manually transcribed from rendered original pages. They are not machine-extracted text or OCR output. Original SHA-256, 1-based PDF pages, displayed raw values, scales, reporting scope and publication evidence are retained.

| Issuer | Scope represented | Publication | Prior comparative availability |
|---|---|---|---|
| FPT | Technology; annual consolidated 2025 | 2026-03-19, day precision | 2024 figures first available in this source on 2026-03-19 |
| SSI | Securities broker; annual consolidated 2025 | 2026-03-27, day precision | 2024 income explicitly restated; publication remains 2026-03-27 |
| VCB | Bank; annual consolidated 2025 | 2026-03-27, day precision | 2024 figures first available in this source on 2026-03-27 |

`published_at` remains null where no time of day was proven. The importer filters by `published_on <= as_of`; it does not manufacture a timestamp. VCB original monetary columns are million VND and canonical values are already converted to VND. Its EPS retains scale 1 and VND/share. SSI basic EPS 2053 and diluted EPS 1939 are different original rows; the erroneous legacy basic EPS equal to total attributable profit is quarantined.

The bundled legacy Parquet and company catalog remain available to Demo and coverage checks. Their original numerical values, units and publication dates are **unverified** unless replaced by a reviewed filing. An empty or not-yet-created configured snapshot directory falls back to this bundled set; a broken declared release manifest fails integrity validation. Historical cutoff filtering cannot make the legacy snapshot point-in-time data. Missing manufacturing/small-cap original-source verification, arbitrary-ticker automatic filings and verified 2026 quarterly refreshes remain outside the checked sample. No 2026 annual statement is invented.

## Automatic filing retrieval

`data.autoload.ensure_fixture_filings(directory, ticker, start, end, as_of, ...)` selects packaged reviewed issuer envelopes, checks the publication cutoff, reuses matching original bytes, and imports immutable releases. It returns `ready`, `partial` or `unavailable`, selected envelopes, release paths, cache/download counts and structured quality issues.

Automatic downloads use only the exact curated report URLs on `fpt.com`, `www.ssi.com.vn` and `www.vietcombank.com.vn`. TLS verification stays enabled. The request uses a 5-second connect timeout, 20-second read timeout, a 30-second elapsed stream bound, maximum 50 MB, no redirects, and no retries. Current/prior envelopes referencing the same original require at most one fetch per call. A 403, changed document hash or missing coverage returns an explicit issue; it does not substitute another document or fabricate facts. The existing saved FPT original was checked even though a repeat request to its official URL returned 403.

The original cache is addressed by SHA-256. Cache reuse verifies its actual bytes. An already installed filing with identical canonical observations, original hash, period, basis and publication date is reused when descriptive notes or local path labels change; metadata-only updates do not create ambiguous same-day revisions. Conflicting observations on the same publication day require explicit release selection and are not silently preferred.

## Financial data and provenance

- `load_raw(tickers, start, end, *, as_of, filing_dir, dataset_dir, period_type)` keeps annual, half-year and quarterly inputs separate. Quarterly/half-year imports can be stored and queried; the annual `extract_facts` and downstream annual-ratio path do not merge them into fake annual figures.
- Snapshot parsing and provenance use the same captured bytes. Content hashes identify cache entries; updated files and catalogs refresh without a process restart. Data returned to callers is copied. `seal-snapshot` creates an immutable file inventory and dataset version; changed or missing declared files fail validation.
- Reviewed consolidated filings replace the whole matching period's legacy fact selection. A missing reviewed fact stays null; it is not backfilled from another statement basis, release or unverified legacy row. Separate statements are explicitly marked when used. A new unverified filing does not overwrite a legacy selection.
- Exact item-code mappings cover company, bank, broker and insurance templates. Bank revenue means total operating income; broker and insurance definitions remain explicit. Conflicting duplicate codes fail; ambiguous aliases are quarantined. No fuzzy substring selects a financial number.
- `extract_facts` returns `fact_metadata` and `quality_issues`, including unit, raw/selected value, mapping version, source ID/hash/page, publication date, statement basis and verification status. Missing and quarantined values remain null. Only all-verified inputs produce a verified derived fact.
- Equity attributable to owners requires the total-equity/NCI accounting basis to reconcile. CAPEX denotes positive expenditure, while signed raw outflows remain in metadata. Positive legacy CAPEX and unexplained negative depreciation are quarantined. Imported signs must agree with their declared convention; they are not silently converted with `abs`.
- EPS guards detect wrong units, profit copied into EPS, extreme basic/diluted disagreement and inconsistency with same-period weighted-average shares. A correct reported EPS is not multiplied by a balance-sheet monetary scale.
- A ticker with statements but no identity record returns unknown company/symbol history plus an issue. Current catalog labels do not certify historic exchange transfers or symbol changes.

## Market data and corporate actions

`data.providers` implements the direct public KBS daily endpoint with an explicit contract derived from the pinned upstream adapter. Prices are VND and volume is shares. Each request is bounded to 366 calendar days, maximum 2 MB by default, 15-second read timeout by default, a minimum 2-second interval, no redirects and no retries. Optional archived raw responses retain their exact SHA-256. A valid response is labelled provider-observed; its adjustment basis remains **unknown**. One historical FPT request was observed during implementation; it does not prove current access for every ticker or all dates. The provider regression suite uses mocked responses.

OHLCV imports reject missing or malformed dates, duplicate sessions, invalid HTTP(S) source URLs, credentials embedded in source URLs, nonpositive prices, nonfinite/overflowing numbers, broken OHLC relationships, fractional/negative/overflowing volume, unknown units and mixed price bases. Inputs after the cutoff are excluded. Synthetic sources are labelled even when supplied outside Demo; stale prices and synthetic production inputs make the market section partial.

With unknown adjustment basis, return, volatility and drawdown stay null. SMA20 describes the observed price series and does not establish adjusted returns. A sourced split input adjusts `analysis_close` for pre-ex-date sessions while preserving raw OHLCV. Cash dividends are recorded but are not fabricated into total return. Future actions are excluded; duplicate actions and adjustment of an already adjusted series fail. Applying a split to unknown-basis prices keeps the analysis basis unknown and returns an issue about possible double adjustment.

There is no automatic corporate-action feed, exchange trading calendar, verified missing-session/suspension classification, total-return reconstruction or instrument transfer history. Corporate actions currently support `split` and `cash_dividend`; rights issues require another explicit contract.

## Data CLI

Use the installed project Python, or set `PYTHONPATH=src` during development. Normal report orchestration calls the automatic bootstrap; no filing upload is required for a covered ticker when matching originals are cached or available publicly.

```powershell
python -m vnresearch.data.cli capabilities
python -m vnresearch.data.cli bootstrap-filings --ticker FPT --start-year 2024 --end-year 2025 --as-of 2026-10-09 --directory var/data/filings
python -m vnresearch.data.cli coverage --ticker FPT --ticker SSI --ticker VCB --ticker ZZZZ --start-year 2024 --end-year 2025 --as-of 2026-10-09 --filing-dir var/data/filings --output var/data/coverage.json
python -m vnresearch.data.cli fetch-prices --ticker FPT --start 2025-09-01 --end 2025-09-30 --directory var/data/market-FPT
python -m vnresearch.data.cli seal-snapshot src/vnresearch/assets/bctc --directory var/data/snapshot-releases
```

`bootstrap-filings --original-cache var/originals` optionally reuses a previously saved original by its sanitized envelope filename. It still checks SHA-256. `fetch-prices` performs one real public request and stores `prices.csv`, `provider.json` and the raw response named by its hash; an unavailable source raises a data error.

Administrative import/validation is available for additional reviewed data:

```powershell
python -m vnresearch.data.cli validate --filing examples/verified-filings/FPT_2025_verified_filing.json --original-document var/originals/FPT_2025_audited_consolidated.pdf
python -m vnresearch.data.cli import-filing examples/verified-filings/FPT_2025_verified_filing.json --directory var/data/filings --original-document var/originals/FPT_2025_audited_consolidated.pdf
$env:VNRESEARCH_FILING_DIR = (Resolve-Path var/data/filings).Path
python -m vnresearch.data.cli coverage --ticker FPT --period-type quarterly --start-year 2026 --end-year 2026 --as-of 2026-10-09 --filing-dir var/data/filings
```

Additional envelopes must declare fiscal year, period start/end/type, consolidated/separate basis, official report URL, original document SHA-256, a supported publication date and financial observations with units. Canonical VND is the default `value_basis`; use `reported` only when `value` still requires multiplication by `scale`. EPS uses VND/share and share counts use shares. Verified imports additionally require matching original bytes, a verification note and source pages. Null observations remain null. Importing supports later annual, quarterly and half-year releases without modifying the packaged legacy files.

Optional corporate-action CSV columns are `ticker,ex_date,action_type,source_url,split_ratio,cash_per_share`. `split_ratio` is new shares / old shares; `cash_per_share` is VND/share. The market function accepts `actions_path`; report-level wiring is owned by the integrating team.

## Validation completed

The focused offline suite passes **105 tests** across the market baseline, data provenance, filing metadata, corporate-action guards, mocked KBS transport and automatic filing retrieval. Ruff passes for the data modules and these tests. All HTTP in pytest is disabled except supplied mock sessions. Offline transport fixtures explicitly identify generated bytes; they are not issuer PDFs. Metadata regressions preserve selected official values and publication evidence but do not redo the visual document review.

The seven curated envelopes were also imported against the actual saved original PDFs through automatic cache bootstrap, separately from the mock suite. Original-byte validation and cutoff checks do not imply all product requirements are complete. Full Web/PDF integration, market-wide source verification, provider availability across ticker/date ranges, sector interpretation and AI/Jev quality remain separate acceptance work. No paid AI requests were used by TV2.

## Integrated automatic run

The combined TV1/TV2 pipeline was run with SSI and all six sections, with no manual CSV uploads. Live KBS prices and dated news were obtained; the original filing cache supplied reviewed annual and H1 observations. Both configured user models, gpt-6-luna and jev-1.13-free, returned validated results. The output PDF/JSON/manifest was generated automatically in about 44 seconds. Report quality remained partial because World Bank timed out, the verified sector cohort was too small, and price adjustment basis remained unknown. Those conditions do not stop automatic publication and do not authorize invented ratios or investment conclusions.
