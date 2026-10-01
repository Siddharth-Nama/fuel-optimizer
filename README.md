# fuel-optimizer

API for a US driving route and the cheapest truck stops to fuel at along it.

The truck gets 10 miles per gallon and can travel 500 miles on a full 50-gallon tank. Prices come from the Spotter CSV. The road comes from one OSRM call.

## Run

macOS / Linux:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python backend/manage.py runserver
```

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
.\venv\Scripts\python backend\manage.py runserver
```

`GET http://127.0.0.1:8000/api/health/` returns `{"status": "ok"}`.

## Plan a trip

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

The response holds the route geometry, the start station, the ordered fuel stops (each with its `route_mile`, gallons bought and CSV price), `trip_gallons` and `total_cost_usd`. Its `map` field is a GeoJSON FeatureCollection with the route line, start and finish points, and one point per fuel stop. Paste it into [geojson.io](https://geojson.io) to see the trip.

Coordinates make one OSRM call. Two city names add at most two Nominatim lookups. Repeat requests reuse in-memory caches: place names until the server restarts, routes for 10 minutes. A repeated trip makes no external calls.

Import `postman/fuel-optimizer.postman_collection.json` into Postman for these trips, a long coast-to-coast trip, a short trip with no stops, and the error cases.

### Response

```text
start, finish     {lat, lng}, plus name when a place name was sent
route             miles, minutes, geometry [{lat, lng}, ...]
fuel              mpg, range_miles, tank_gallons, trip_gallons, total_cost_usd,
                  start_station {name, city, state, price_per_gallon, lat, lng, route_mile, gallons, cost_usd, ...},
                  stops [{same fields}, ...] in road order
map               GeoJSON FeatureCollection: copy this value into geojson.io
```

### Errors

Every error returns `{"error": "..."}`.

- `400`: the body isn't JSON, `start` or `finish` is missing or empty, a coordinate isn't a number, a place is outside the contiguous United States, or no road connects start and finish.
- `422`: no truck stop within 500 miles of the start, or a stretch of road longer than 500 miles with no truck stop.
- `502`: Nominatim or OSRM is down or too slow. Sending coordinates avoids Nominatim.

## How the fuel plan works

1. The start station is the first truck stop the truck reaches on the road.
2. The tank starts full (500 miles) and is priced at the start station's CSV price.
3. If the finish is within 500 miles, there are no stops.
4. Otherwise, at each point the truck looks ahead one full tank (500 miles):
   - If a cheaper stop is in range, it buys just enough to reach the nearest one. It skips the more expensive stops in between.
   - If no cheaper stop is in range, it fills up. If the finish is closer, it buys only enough to reach the finish. After filling up, it drives to the cheapest stop in range.
5. The trip is charged only for fuel it burns:
   - The starting tank costs start price × the gallons used from it.
   - Each stop costs gallons bought × that stop's price.
   - `total_cost_usd` is the sum of those costs, so it is never $0. A 300-mile trip makes no stops and costs 30 × the start price.
6. `trip_gallons` is always route miles / 10. The gallons charged add up to it.
