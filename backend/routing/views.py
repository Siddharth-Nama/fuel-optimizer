import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from routing.fuel import FuelPlanError, fuel_plan
from routing.geo import InvalidLocation, parse_location, require_usa
from routing.maps import MapServiceError, geocode, route
from routing.route import mile_markers
from routing.stations import stations_along_route


def health(request):
    return JsonResponse({"status": "ok"})


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _resolve(point, field, calls):
    if "lat" in point:
        return require_usa(point, field)
    return geocode(point["name"], field, calls)


def _station_json(station):
    return {
        "opis_id": station["opis_id"],
        "name": station["name"],
        "address": station["address"],
        "city": station["city"],
        "state": station["state"],
        "price_per_gallon": station["price"],
        "lat": station["lat"],
        "lng": station["lng"],
        "route_mile": round(station["route_mile"], 1),
        "gallons": round(station["gallons"], 2),
        "cost_usd": round(station["cost_usd"], 2),
    }


@csrf_exempt
@require_POST
def plan_route(request):
    try:
        body = json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return _error("Request body must be a JSON object.")

    calls = {"nominatim": 0, "osrm": 0}
    try:
        start = parse_location(body.get("start"), "start")
        finish = parse_location(body.get("finish"), "finish")
        start = _resolve(start, "start", calls)
        finish = _resolve(finish, "finish", calls)
        road = route(start, finish, calls)
    except InvalidLocation as exc:
        return _error(str(exc))
    except MapServiceError:
        return _error("A map service is unavailable. Try again, or send coordinates to skip geocoding.", 502)

    points = mile_markers(road["coordinates"], road["miles"])
    try:
        plan = fuel_plan(stations_along_route(points), road["miles"])
    except FuelPlanError as exc:
        return _error(str(exc), 422)

    return JsonResponse(
        {
            "start": start,
            "finish": finish,
            "route": {
                "miles": round(road["miles"], 1),
                "minutes": round(road["minutes"]),
                "geometry": [{"lat": point["lat"], "lng": point["lng"]} for point in points],
            },
            "fuel": {
                "mpg": plan["mpg"],
                "range_miles": plan["range_miles"],
                "tank_gallons": plan["tank_gallons"],
                "trip_gallons": round(plan["trip_gallons"], 2),
                "total_cost_usd": round(plan["total_cost_usd"], 2),
                "start_station": _station_json(plan["start_station"]),
                "stops": [_station_json(stop) for stop in plan["stops"]],
            },
            "external_calls": calls,
        }
    )
