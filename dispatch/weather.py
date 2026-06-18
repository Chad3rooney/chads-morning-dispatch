"""Local weather via Open-Meteo — free, keyless, CORS-enabled (so it also
refreshes client-side). Used for the Port Stephens Brief.
"""

from . import http

API = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,precipitation"
       "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
       "&timezone=Australia%2FSydney&forecast_days=2")

# WMO weather codes -> (short text, emoji)
WMO = {
    0: ("Clear", "☀️"), 1: ("Mainly clear", "\U0001f324️"),
    2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "\U0001f32b️"), 48: ("Rime fog", "\U0001f32b️"),
    51: ("Light drizzle", "\U0001f326️"), 53: ("Drizzle", "\U0001f326️"),
    55: ("Heavy drizzle", "\U0001f327️"), 56: ("Freezing drizzle", "\U0001f327️"),
    57: ("Freezing drizzle", "\U0001f327️"), 61: ("Light rain", "\U0001f326️"),
    63: ("Rain", "\U0001f327️"), 65: ("Heavy rain", "\U0001f327️"),
    66: ("Freezing rain", "\U0001f327️"), 67: ("Freezing rain", "\U0001f327️"),
    71: ("Light snow", "\U0001f328️"), 73: ("Snow", "\U0001f328️"),
    75: ("Heavy snow", "❄️"), 77: ("Snow grains", "\U0001f328️"),
    80: ("Light showers", "\U0001f326️"), 81: ("Showers", "\U0001f327️"),
    82: ("Heavy showers", "⛈️"), 85: ("Snow showers", "\U0001f328️"),
    86: ("Snow showers", "\U0001f328️"), 95: ("Thunderstorm", "⛈️"),
    96: ("Storm + hail", "⛈️"), 99: ("Storm + hail", "⛈️"),
}


def describe(code):
    return WMO.get(code, ("—", "\U0001f321️"))


def fetch_weather(lat, lon, timeout=12):
    """Return a dict of current + today/tomorrow weather, or None on failure."""
    data = http.get_json(API.format(lat=lat, lon=lon), timeout=timeout, retries=2)
    try:
        cur = data["current"]
        day = data["daily"]
    except (TypeError, KeyError):
        return None
    text, emoji = describe(cur.get("weather_code"))
    out = {
        "temp": cur.get("temperature_2m"),
        "code": cur.get("weather_code"),
        "text": text, "emoji": emoji,
        "wind": cur.get("wind_speed_10m"),
        "humidity": cur.get("relative_humidity_2m"),
        "precip": cur.get("precipitation"),
    }
    try:
        out["today_max"] = day["temperature_2m_max"][0]
        out["today_min"] = day["temperature_2m_min"][0]
        out["today_rain"] = day["precipitation_probability_max"][0]
        out["tom_max"] = day["temperature_2m_max"][1]
        out["tom_min"] = day["temperature_2m_min"][1]
        tt, te = describe(day["weather_code"][1])
        out["tom_text"] = tt
    except (KeyError, IndexError, TypeError):
        pass
    return out
