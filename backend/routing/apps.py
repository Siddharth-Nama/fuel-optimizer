from django.apps import AppConfig


class RoutingConfig(AppConfig):
    name = "routing"

    def ready(self):
        from routing.stations import get_stations

        get_stations()
