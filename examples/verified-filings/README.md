# Selected original filing observations

Seven envelopes contain **51 visually checked observations** from audited consolidated issuer statements: 11 current-year facts and 4 prior-year comparative facts for each of FPT, SSI and VCB. They preserve the official URL, original document SHA-256, PDF page, raw displayed value, scale, statement scope and publication evidence. These are selected observations; they do not certify the complete statements or every legacy snapshot row.

| Issuer | Source report | Publication proven to day | Current facts | Prior comparative facts | Original PDF SHA-256 |
|---|---|---|---:|---:|---|
| FPT | 2025 audited consolidated | 2026-03-19 | 11 | 4 | `630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4` |
| SSI | 2025 audited consolidated | 2026-03-27 | 11 | 4 | `406da3dfc1130da4c47b4e08c81c7ab1fd82a8e0bbe225af08b6fcb62cb91625` |
| VCB | 2025 audited consolidated | 2026-03-27 | 11 | 4 | `295f397de287f84c26dafbfa06f668604aa696a013e236253149d8547d032d1f` |

All seven have `published_at: null` and `publication_precision: day`. Prior comparatives retain the publication date of their 2025 source report; their fiscal year does not authorize backdating availability. SSI comparative income is explicitly restated. FPT/VCB comparative statements are not assigned an invented restatement assertion. VCB original money columns use million VND; the canonical observations already use VND, while EPS remains VND/share with scale 1.

The four original PDFs were visually reviewed from saved scans. They are kept outside Git. Metadata filenames replace the author's absolute machine paths. Download each exact `report_url` from the corresponding envelope into `var/originals/` before importing. Repeat downloads can fail (the repeat FPT request returned HTTP 403); the importer requires matching original bytes and never silently substitutes another document.

From the repository root, with the project installed:

```powershell
python -m vnresearch.data.cli import-filing examples/verified-filings/FPT_2025_verified_filing.json --directory var/data/filings --original-document var/originals/FPT_2025_audited_consolidated.pdf
python -m vnresearch.data.cli import-filing examples/verified-filings/FPT_2024_comparative_verified_filing.json --directory var/data/filings --original-document var/originals/FPT_2025_audited_consolidated.pdf
python -m vnresearch.data.cli import-filing examples/verified-filings/SSI_2025_verified_filing.json --directory var/data/filings --original-document var/originals/SSI_2025_audited_consolidated.pdf
python -m vnresearch.data.cli import-filing examples/verified-filings/SSI_2024_comparative_verified_filing.json --directory var/data/filings --original-document var/originals/SSI_2025_audited_consolidated.pdf
python -m vnresearch.data.cli import-filing examples/verified-filings/VCB_2025_verified_filing.json --directory var/data/filings --original-document var/originals/VCB_2025_audited_consolidated.pdf
python -m vnresearch.data.cli import-filing examples/verified-filings/VCB_2024_comparative_verified_filing.json --directory var/data/filings --original-document var/originals/VCB_2025_audited_consolidated.pdf
$env:VNRESEARCH_FILING_DIR = (Resolve-Path var/data/filings).Path
python -m vnresearch.data.cli coverage --ticker FPT --ticker SSI --ticker VCB --start-year 2024 --end-year 2025 --as-of 2026-10-09 --filing-dir var/data/filings --output var/data/coverage.json
```

Each import stores an immutable content-addressed `filing.json` plus the exact original document in the ignored runtime directory. Imports without an original document cannot accept `verification_status: verified`. A failed checksum aborts the import. Editing a stored release invalidates its identity; create a new envelope and import a new release instead.

See [TV2 implementation and CLI](../../docs/TV2_IMPLEMENTATION.md) for supported operations and remaining acceptance limits.

## New 2026 period

`SSI_2026_H1_verified_filing.json` records six selected observations from the reviewed consolidated half-year report for 2026-01-01 through 2026-06-30, published on 2026-08-14 to day precision. The exact source document hash is `9b9e03bf94162dd46dcc9ad5ede2e7ce3fc4f541e9a4b895f5fe7f3ef7990dee`. Its EPS is 1,033 VND/share for that half-year; it does not replace annual 2025 basic EPS 2,053 or define an annual/TTM EPS.

Automatic retrieval uses the packaged seed metadata, publication cutoff, exact original hash and a bounded official-URL downloader. Manual `import-filing` is an administration option, not a required user step. A blocked/changed source yields a quality issue and partial output.
