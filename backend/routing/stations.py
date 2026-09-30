import csv
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "fuel-prices-for-be-assessment.csv"


def load_stations(path=DATA_PATH):
    """Read truck stops from the Spotter price file.

    Rows with a blank or unreadable price are skipped. The same OPIS id
    is kept once.
    """
    stations = []
    seen = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            opis_id = (row.get("OPIS Truckstop ID") or "").strip()
            raw_price = (row.get("Retail Price") or "").strip()
            if not opis_id or not raw_price or opis_id in seen:
                continue
            try:
                price = float(raw_price)
            except ValueError:
                continue
            seen.add(opis_id)
            stations.append(
                {
                    "opis_id": opis_id,
                    "name": (row.get("Truckstop Name") or "").strip(),
                    "address": (row.get("Address") or "").strip(),
                    "city": (row.get("City") or "").strip(),
                    "state": (row.get("State") or "").strip(),
                    "price": price,
                }
            )
    return stations
