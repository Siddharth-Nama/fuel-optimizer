import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from routing.geo import InvalidLocation, parse_location, require_usa


def health(request):
    return JsonResponse({"status": "ok"})


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


@csrf_exempt
@require_POST
def plan_route(request):
    try:
        body = json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("Request body must be valid JSON.")
    if not isinstance(body, dict):
        return _error("Request body must be a JSON object.")

    try:
        start = parse_location(body.get("start"), "start")
        finish = parse_location(body.get("finish"), "finish")
        for point, field in ((start, "start"), (finish, "finish")):
            if "lat" in point:
                require_usa(point, field)
    except InvalidLocation as exc:
        return _error(str(exc))

    return JsonResponse({"start": start, "finish": finish})
