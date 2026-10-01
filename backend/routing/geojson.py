def _point(lat, lng, properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
    }


def _stop_properties(stop, label, color):
    return {
        "name": f"{label}: {stop['name']}",
        "city": f"{stop['city']}, {stop['state']}",
        "price_per_gallon": stop["price_per_gallon"],
        "gallons": stop["gallons"],
        "cost_usd": stop["cost_usd"],
        "route_mile": stop["route_mile"],
        "marker-color": color,
        "marker-symbol": "fuel",
    }


def trip_map(start, finish, geometry, start_station, stops):
    """A GeoJSON FeatureCollection that geojson.io draws as-is.

    marker-color, stroke and similar keys follow the simplestyle spec geojson.io reads.
    """
    features = [
        {
            "type": "Feature",
            "properties": {"name": "Route", "stroke": "#2563eb", "stroke-width": 4},
            "geometry": {
                "type": "LineString",
                "coordinates": [[point["lng"], point["lat"]] for point in geometry],
            },
        },
        _point(start["lat"], start["lng"], {"name": f"Start: {start.get('name', 'start')}", "marker-color": "#16a34a", "marker-symbol": "s"}),
        _point(finish["lat"], finish["lng"], {"name": f"Finish: {finish.get('name', 'finish')}", "marker-color": "#dc2626", "marker-symbol": "f"}),
        _point(start_station["lat"], start_station["lng"], _stop_properties(start_station, "Starting tank priced here", "#6b7280")),
    ]
    for number, stop in enumerate(stops, 1):
        features.append(_point(stop["lat"], stop["lng"], _stop_properties(stop, f"Fuel stop {number}", "#f59e0b")))
    return {"type": "FeatureCollection", "features": features}
