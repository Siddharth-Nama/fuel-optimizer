# fuel-optimizer

API for a US driving route and the cheapest truck stops to fuel at along it.

The truck starts with a full tank, gets 10 miles per gallon, and can travel 500 miles on that tank. Prices come from the Spotter CSV. The road comes from one OSRM call.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python backend\manage.py runserver
```

`POST http://127.0.0.1:8000/api/route/plan/`

```json
{ "start": "Dallas, TX", "finish": "Denver, CO" }
```

```json
{
  "start": { "lat": 32.7767, "lng": -96.797 },
  "finish": { "lat": 39.7392, "lng": -104.9903 }
}
```

Coordinates make one OSRM call. Two city names add at most two Nominatim lookups. Repeat requests reuse an in-memory cache. Import `postman/fuel-optimizer.postman_collection.json` for the same calls.

## Assumptions

- The tank starts full (50 gallons). `total_cost_usd` is money paid at pumps on this trip. A trip under 500 miles can cost $0.
- `trip_gallons` is always route miles / 10.
- A stop counts when it sits within 8 miles of the driven road.
- The CSV has no coordinates. `scripts/build_station_index.py` resolves each US highway exit once into `data/stations_geocoded.json`. The API does not geocode stops.
- Canadian rows in the CSV are skipped.

```
