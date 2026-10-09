"""Freeze a real World Bank snapshot. Fail without replacing an existing snapshot on provider errors."""
from datetime import date

from vnresearch.macro.provider import fetch_world_bank
from vnresearch.platform.settings import ASSETS

frame = fetch_world_bank(date.today().year - 6, date.today().year - 1)
if frame.empty:
    raise SystemExit("World Bank returned no observations; existing data unchanged")
output = ASSETS / "macro/world_bank.csv"
output.parent.mkdir(parents=True, exist_ok=True)
temporary = output.with_suffix(".csv.tmp")
frame.to_csv(temporary, index=False)
temporary.replace(output)
print(f"Saved {len(frame)} observations to {output}")
