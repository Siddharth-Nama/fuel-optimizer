from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(a))


def mile_markers(coordinates, road_miles):
    """Turn OSRM [lng, lat] pairs into points that know how far along the road they are.

    A simplified line cuts corners, so it is shorter than the road. Scaling by
    OSRM's own distance makes the last point land on the real trip length.
    """
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
