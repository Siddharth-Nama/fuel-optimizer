from rest_framework.decorators import api_view
from rest_framework.exceptions import ParseError
from rest_framework.response import Response

from routing.fuel import FuelPlanError, fuel_plan
from routing.geo import InvalidLocation, require_usa
from routing.geojson import trip_map
from routing.maps import MapServiceError, geocode, route
from routing.route import mile_markers
from routing.serializers import RouteRequestSerializer, StationSerializer
from routing.stations import stations_along_route


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


def _error(message, status=400):
    return Response({"error": message}, status=status)


def _first_error(errors):
    messages = next(iter(errors.values()))
    return str(messages[0])


def _resolve(point, field):
    if "lat" in point:
        return require_usa(point, field)
    return geocode(point["name"], field)


@api_view(["POST"])
def plan_route(request):
    try:
        body = request.data
    except ParseError:
        return _error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return _error("Request body must be a JSON object.")

    request_serializer = RouteRequestSerializer(data=body)
    if not request_serializer.is_valid():
        return _error(_first_error(request_serializer.errors))

    try:
        start = _resolve(request_serializer.validated_data["start"], "start")
        finish = _resolve(request_serializer.validated_data["finish"], "finish")
        road = route(start, finish)
    except InvalidLocation as exc:
        return _error(str(exc))
    except MapServiceError:
        return _error("A map service is unavailable. Try again, or send coordinates to skip geocoding.", 502)

    points = mile_markers(road["coordinates"], road["miles"])
    try:
        plan = fuel_plan(stations_along_route(points), road["miles"])
    except FuelPlanError as exc:
        return _error(str(exc), 422)

    geometry = [{"lat": point["lat"], "lng": point["lng"]} for point in points]
    start_station = StationSerializer(plan["start_station"]).data
    stops = StationSerializer(plan["stops"], many=True).data

    return Response(
        {
            "start": start,
            "finish": finish,
            "route": {
                "miles": round(road["miles"], 1),
                "minutes": round(road["minutes"]),
                "geometry": geometry,
            },
            "fuel": {
                "mpg": plan["mpg"],
                "range_miles": plan["range_miles"],
                "tank_gallons": plan["tank_gallons"],
                "trip_gallons": round(plan["trip_gallons"], 2),
                "total_cost_usd": round(plan["total_cost_usd"], 2),
                "start_station": start_station,
                "stops": stops,
            },
            # Paste this value into geojson.io to see the road and the stops.
            "map": trip_map(start, finish, geometry, start_station, stops),
        }
    )
