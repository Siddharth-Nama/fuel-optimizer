from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(a))


def mile_markers(coordinates, road_miles):
    points = []
    traveled = 0.0
    for index, (lng, lat) in enumerate(coordinates):
        if index:
            prev = points[-1]
            traveled += haversine_miles(prev["lat"], prev["lng"], lat, lng)
        points.append({"lat": lat, "lng": lng, "mile": traveled})

    if traveled > 0:
        scale = road_miles / traveled
        for point in points:
            point["mile"] *= scale
    return points


def project(a, b, lat, lng):
    lng_scale = 69.0 * cos(radians(lat))
    ax, ay = (a["lng"] - lng) * lng_scale, (a["lat"] - lat) * 69.0
    bx, by = (b["lng"] - lng) * lng_scale, (b["lat"] - lat) * 69.0
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else -(ax * dx + ay * dy) / length_sq
    clamped = min(1.0, max(0.0, t))
    return sqrt((ax + clamped * dx) ** 2 + (ay + clamped * dy) ** 2), t
