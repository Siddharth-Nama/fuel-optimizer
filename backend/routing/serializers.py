from rest_framework import serializers

from routing.geo import InvalidLocation, parse_location


class LocationField(serializers.Field):
    """A place name ("Dallas, TX") or an object with lat and lng."""

    def to_internal_value(self, data):
        try:
            return parse_location(data, self.field_name)
        except InvalidLocation as exc:
            raise serializers.ValidationError(str(exc)) from None

    def to_representation(self, value):
        return value


def _location(field):
    missing = f"{field} is required."
    return LocationField(error_messages={"required": missing, "null": missing})


class RouteRequestSerializer(serializers.Serializer):
    start = _location("start")
    finish = _location("finish")


class RoundedFloatField(serializers.FloatField):
    def __init__(self, digits, **kwargs):
        self.digits = digits
        super().__init__(**kwargs)

    def to_representation(self, value):
        return round(super().to_representation(value), self.digits)


class StationSerializer(serializers.Serializer):
    opis_id = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    price_per_gallon = serializers.FloatField(source="price")
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    route_mile = RoundedFloatField(digits=1)
    gallons = RoundedFloatField(digits=2)
    cost_usd = RoundedFloatField(digits=2)
