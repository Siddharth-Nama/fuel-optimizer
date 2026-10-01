from django.urls import path

from routing import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("route/plan/", views.plan_route, name="plan-route"),
]
