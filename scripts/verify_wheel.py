"""Install the built wheel outside the source checkout and verify an offline report and package assets."""
from pathlib import Path
import os
import subprocess
import tempfile
import venv


root = Path(__file__).resolve().parents[1]
wheels = sorted((root / "dist").glob("vn_investment_research-*.whl"))
if len(wheels) != 1:
    raise SystemExit("Build exactly one wheel before verification")
with tempfile.TemporaryDirectory(prefix="vnresearch-wheel-") as directory:
    temporary = Path(directory)
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH" and not k.startswith(("LLM_", "JEV_", "TYPESAFE_"))}
    environment["PYTHONUTF8"] = "1"
    venv.create(temporary / "venv", with_pip=True)
    executable = temporary / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(executable), "-m", "pip", "install", str(wheels[0])], check=True, cwd=temporary, env=environment)
    code = """
import hashlib,json,pathlib,sys
import vnresearch
from vnresearch.platform.settings import ASSETS
assert pathlib.Path(vnresearch.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix))
assert len(list((ASSETS/'bctc').glob('*/*.parquet')))==6
assert (ASSETS/'fonts/DejaVuSans.ttf').is_file()
assert (ASSETS.parent/'static/app.js').is_file()
from vnresearch.cli import main
sys.argv=['vnresearch','report','--ticker','FPT','--mode','demo','--start-year','2022','--end-year','2025','--output','report']
main()
folder=pathlib.Path('report')
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
for name,item in manifest['files'].items():
 assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==item['sha256']
print('Installed wheel, offline report and hashes verified')
"""
    subprocess.run([str(executable), "-c", code], check=True, cwd=temporary, env=environment)
