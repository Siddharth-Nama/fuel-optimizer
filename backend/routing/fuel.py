RANGE_MILES = 500
MPG = 10


class FuelPlanError(Exception):
    """The trip cannot be fuelled from the CSV stops (the API answers 422)."""

def _stop_for(station):
    return {key: station[key] for key in ("opis_id", "name", "address", "city", "state", "price", "lat", "lng", "route_mile")}


def plan_stops(stations, total_miles, range_miles=RANGE_MILES):
    if not stations or stations[0]["route_mile"] > range_miles:
        raise FuelPlanError(f"No truck stop within {range_miles} miles of the start.")

    start_station = stations[0]
    position = 0.0
    price = start_station["price"]
    fuel = float(range_miles)  
    here = None 
    stops = []

    def buy(miles):
        nonlocal fuel
        if miles > 0 and here is not None:
            stops.append({**_stop_for(stations[here]), "miles_bought": miles})
            fuel += miles

    while total_miles - position > fuel:
        first = 0 if here is None else here + 1
        ahead = [
            index
            for index in range(first, len(stations))
            if stations[index]["route_mile"] - position <= range_miles
        ]
        cheaper = next((index for index in ahead if stations[index]["price"] < price), None)

        if cheaper is not None:
            buy(stations[cheaper]["route_mile"] - position - fuel)
            target = cheaper
        elif total_miles - position <= range_miles:
            buy(total_miles - position - fuel)
            break
        elif ahead:
            buy(range_miles - fuel)
            target = min(ahead, key=lambda index: (stations[index]["price"], -stations[index]["route_mile"]))
        else:
            raise FuelPlanError(
                f"No truck stop within {range_miles} miles after mile {position:.0f}; the truck would run dry."
            )

        fuel -= stations[target]["route_mile"] - position
        position = stations[target]["route_mile"]
        price = stations[target]["price"]
        here = target

    return {"start_station": _stop_for(start_station), "stops": stops}


def fuel_plan(stations, total_miles, range_miles=RANGE_MILES, mpg=MPG):
    plan = plan_stops(stations, total_miles, range_miles)
    tank_gallons = range_miles / mpg
    trip_gallons = total_miles / mpg

    stops = []
    for stop in plan["stops"]:
        gallons = stop.pop("miles_bought") / mpg
        stops.append({**stop, "gallons": gallons, "cost_usd": gallons * stop["price"]})

    start_gallons = min(tank_gallons, trip_gallons)
    start_station = plan["start_station"]
    start_cost = start_gallons * start_station["price"]

    return {
        "start_station": {**start_station, "gallons": start_gallons, "cost_usd": start_cost},
        "stops": stops,
        "mpg": mpg,
        "range_miles": range_miles,
        "tank_gallons": tank_gallons,
        "trip_gallons": trip_gallons,
        "total_cost_usd": start_cost + sum(stop["cost_usd"] for stop in stops),
    }
