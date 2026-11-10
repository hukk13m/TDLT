"""Weather lookup with an offline fallback.

Uses Open-Meteo because it needs no API key and no registration: one plain
HTTPS GET. Results are cached in SQLite for 30 minutes so the app keeps
working when the demo room has no Wi-Fi - in that case the screen says
"offline estimate" instead of showing an error.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from libs.models import Context

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_MINUTES = 30

# WMO weather interpretation codes -> (label, is_rain)
WMO = {
    0: ("Clear", False), 1: ("Mostly Clear", False), 2: ("Partly Cloudy", False),
    3: ("Overcast", False), 45: ("Foggy", False), 48: ("Foggy", False),
    51: ("Light Drizzle", True), 53: ("Drizzle", True), 55: ("Heavy Drizzle", True),
    61: ("Light Rain", True), 63: ("Rain", True), 65: ("Heavy Rain", True),
    66: ("Freezing Rain", True), 67: ("Freezing Rain", True),
    71: ("Light Snow", False), 73: ("Snow", False), 75: ("Heavy Snow", False),
    80: ("Rain Showers", True), 81: ("Rain Showers", True), 82: ("Violent Showers", True),
    95: ("Thunderstorm", True), 96: ("Thunderstorm", True), 99: ("Thunderstorm", True),
}

# HCMC-ish monthly means used when the network is unavailable.
SEASONAL_FALLBACK = {
    1: (32, "Clear"), 2: (33, "Clear"), 3: (34, "Mostly Clear"),
    4: (35, "Partly Cloudy"), 5: (34, "Rain Showers"), 6: (32, "Rain Showers"),
    7: (31, "Rain Showers"), 8: (31, "Rain Showers"), 9: (31, "Rain Showers"),
    10: (31, "Partly Cloudy"), 11: (31, "Partly Cloudy"), 12: (31, "Clear"),
}


def fetch(lat: float, lon: float, timeout: float = 6.0) -> dict:
    query = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": "temperature_2m,apparent_temperature,weather_code",
        "timezone": "auto",
    })
    request = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "AclosetStudio/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    current = payload.get("current", {})
    code = int(current.get("weather_code", 0))
    label, is_rain = WMO.get(code, ("Clear", False))
    return {
        "temperature": float(current.get("temperature_2m", 30)),
        "feels_like": float(current.get("apparent_temperature", 30)),
        "condition": label,
        "is_rain": is_rain,
        "code": code,
        "source": "live",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def seasonal(today: date | None = None) -> dict:
    today = today or date.today()
    temperature, label = SEASONAL_FALLBACK[today.month]
    return {
        "temperature": float(temperature),
        "feels_like": float(temperature),
        "condition": label,
        "is_rain": label in ("Rain Showers", "Rain"),
        "code": 80 if label == "Rain Showers" else 0,
        "source": "offline",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def get_weather(repo, lat: float = 10.8231, lon: float = 106.6297,
                max_age_minutes: int = CACHE_MINUTES) -> dict:
    """Live -> cache -> seasonal fallback, in that order."""
    cached = repo.get_weather_cache()
    if cached and cached.get("fetched_at"):
        try:
            age = datetime.now() - datetime.fromisoformat(cached["fetched_at"])
            if age < timedelta(minutes=max_age_minutes):
                return cached
        except ValueError:
            pass
    try:
        data = fetch(lat, lon)
        repo.set_weather_cache(data)
        return data
    except Exception:  # noqa: BLE001 - any network problem degrades gracefully
        if cached:
            cached["source"] = "cached"
            return cached
        return seasonal()


def cached_or_seasonal(repo) -> dict:
    """Non-blocking fallback used when the live request already failed."""
    cached = repo.get_weather_cache()
    if cached:
        cached["source"] = "cached"
        return cached
    return seasonal()


def apply_to_context(context: Context, weather: dict) -> Context:
    context.temperature = weather.get("temperature", context.temperature)
    context.condition = weather.get("condition", context.condition)
    context.is_rain = bool(weather.get("is_rain", context.is_rain))
    return context
