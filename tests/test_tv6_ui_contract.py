from pathlib import Path


def test_tv6_structure_exists():
    root = Path(__file__).parents[1]
    required = [
        root / "src/vnresearch/static/index.html",
        root / "src/vnresearch/static/app.js",
        root / "src/vnresearch/static/style.css",
        root / "demo/fixtures/demo_report.json",
        root / "demo/create_demo_pdf.py",
        root / "docs/team/tv6-demo-qa.md",
    ]
    assert all(path.exists() for path in required)
    html = (root / "src/vnresearch/static/index.html").read_text(encoding="utf-8")
    script = (root / "src/vnresearch/static/app.js").read_text(encoding="utf-8")
    assert html.count('rel="stylesheet"') == 1
    assert "NHÓM 4" in html
    assert 'id="llmBaseUrl"' in html and 'id="llmApiKey"' in html
    assert 'id="jevBaseUrl"' in html and 'id="jevApiKey"' in html
    assert "const isLoss = d.ni < 0;" in script
