import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request, send_from_directory
from openai import AuthenticationError, OpenAI, OpenAIError, RateLimitError

app = Flask(__name__, static_folder="static")

_client: OpenAI | None = None
_messages: list[dict] = []
_pending_location: bool = False


def load_env_file(path: str = "key.env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"Could not find {path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, separator, value = line.partition("=")
        if not separator:
            continue
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "world-agent/0.1"})
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def normalize_location_name(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", value)
    ascii_text = without_accents.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def clean_location_query(value: str) -> str:
    cleaned = value.strip(" ?.")
    cleaned = re.sub(
        r"\b(right now|as of now|currently|current|today|tonight|tomorrow|please)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip(" ?.,")


def celsius_to_fahrenheit(value: float | int | None) -> str | None:
    if value is None:
        return None

    return f"{(float(value) * 9 / 5) + 32:.1f}"


class WeatherSubAgent:
    def run(self, location: str) -> dict:
        location = clean_location_query(location)
        geocode = self._resolve_city(location)
        latitude = geocode["latitude"]
        longitude = geocode["longitude"]
        weather_url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "timezone": "auto",
        })
        data = get_json(weather_url)
        current = data["current"]
        temperature_c = current.get("temperature_2m")

        return {
            "location": self._format_location(geocode),
            "latitude": str(latitude),
            "longitude": str(longitude),
            "temperature_c": temperature_c,
            "temperature_f": celsius_to_fahrenheit(temperature_c),
            "weather_type": WEATHER_CODES.get(current.get("weather_code"), "Unknown"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "current_time": current.get("time"),
            "timezone": data.get("timezone", geocode.get("timezone", "Unavailable")),
        }

    def _resolve_city(self, requested_location: str) -> dict:
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({
            "name": requested_location,
            "count": 5,
            "language": "en",
            "format": "json",
        })
        data = get_json(geocode_url)
        results = data.get("results") or []
        requested_name = normalize_location_name(requested_location)

        for result in results:
            result_name = normalize_location_name(result.get("name", ""))
            if result_name == requested_name:
                return result

        if not results:
            raise ValueError(f"No city named '{requested_location}' was found.")

        possible_matches = ", ".join(self._format_location(result) for result in results[:3])
        raise ValueError(
            f"I found possible matches for '{requested_location}' but none matched exactly. "
            f"Please be more specific. Possible matches: {possible_matches}"
        )

    @staticmethod
    def _format_location(location: dict) -> str:
        return ", ".join(
            part for part in [
                location.get("name"),
                location.get("admin1"),
                location.get("country"),
            ]
            if part
        )


class TimeSubAgent:
    def run(self, latitude: str | None, longitude: str | None) -> dict:
        if not latitude or not longitude:
            return {"current_time": "Unavailable", "timezone": "Unavailable"}
        url = "https://www.timeapi.io/api/Time/current/coordinate?" + urlencode({
            "latitude": latitude,
            "longitude": longitude,
        })
        data = get_json(url)
        return {
            "current_time": data.get("dateTime") or data.get("time") or "Unavailable",
            "timezone": data.get("timeZone") or data.get("timezone") or "Unavailable",
        }


def is_current_conditions_request(message: str) -> bool:
    text = message.lower()
    keywords = {"temperature", "weather", "humidity", "current conditions", "forecast", "time"}
    return any(keyword in text for keyword in keywords)


def extract_location(message: str) -> str:
    text = message.strip()
    lower_text = text.lower()
    for marker in (" in ", " for ", " at "):
        idx = lower_text.rfind(marker)
        if idx != -1:
            return clean_location_query(text[idx + len(marker):])
    return ""


def split_locations(location_text: str) -> list[str]:
    normalized = clean_location_query(location_text)
    normalized = re.sub(r"\s+(and|&)\s+", ",", normalized, flags=re.IGNORECASE)
    parts = re.split(r"[,;]+", normalized)
    return [clean_location_query(p) for p in parts if clean_location_query(p)]


def get_weather_data(location_text: str) -> list[dict]:
    locations = split_locations(location_text)
    results = []
    weather_agent = WeatherSubAgent()
    time_agent = TimeSubAgent()
    for location in locations:
        try:
            weather = weather_agent.run(location)
            time_info = {
                "current_time": weather.get("current_time"),
                "timezone": weather.get("timezone"),
            }
            if not time_info["current_time"]:
                time_info = time_agent.run(weather["latitude"], weather["longitude"])
            results.append({
                "location": weather["location"] or location,
                "temperature_c": weather["temperature_c"],
                "temperature_f": weather["temperature_f"],
                "weather_type": weather["weather_type"],
                "humidity_percent": weather["humidity_percent"],
                "current_time": time_info["current_time"],
                "timezone": time_info["timezone"],
                "error": None,
            })
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as err:
            results.append({"location": location, "error": str(err)})
    return results


def weather_to_text(data: list[dict]) -> str:
    parts = []
    for d in data:
        if d.get("error"):
            parts.append(f"Could not retrieve data for {d['location']}: {d['error']}")
        else:
            parts.append(
                f"Current data for {d['location']}:\n"
                f"- Temperature: {d['temperature_c']}°C / {d['temperature_f']}°F\n"
                f"- Time: {d['current_time']} ({d['timezone']})\n"
                f"- Weather: {d['weather_type']}\n"
                f"- Humidity: {d['humidity_percent']}%"
            )
    return "\n\n".join(parts)


def get_ai_client() -> OpenAI:
    global _client
    if _client is None:
        load_env_file()
        _client = OpenAI(
            api_key=os.environ["PARALLEL_API_KEY"],
            base_url="https://api.parallel.ai",
        )
    return _client


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    global _messages, _pending_location

    data = request.get_json()
    user_message = (data or {}).get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    if not _messages:
        _messages = [{
            "role": "system",
            "content": "You are my first world agent. Be concise, curious, and helpful.",
        }]

    if _pending_location:
        _pending_location = False
        weather_data = get_weather_data(user_message)
        _messages.append({"role": "user", "content": user_message})
        _messages.append({"role": "assistant", "content": weather_to_text(weather_data)})
        return jsonify({"type": "weather", "data": weather_data})

    if is_current_conditions_request(user_message):
        location = extract_location(user_message)
        if not location:
            _pending_location = True
            reply = "Which city or location should I check right now?"
            _messages.append({"role": "user", "content": user_message})
            _messages.append({"role": "assistant", "content": reply})
            return jsonify({"type": "text", "content": reply})
        weather_data = get_weather_data(location)
        _messages.append({"role": "user", "content": user_message})
        _messages.append({"role": "assistant", "content": weather_to_text(weather_data)})
        return jsonify({"type": "weather", "data": weather_data})

    _messages.append({"role": "user", "content": user_message})

    try:
        client = get_ai_client()
        response = client.chat.completions.create(model="speed", messages=_messages)
    except AuthenticationError:
        return jsonify({"type": "error", "content": "API key rejected — check PARALLEL_API_KEY in key.env."})
    except RateLimitError:
        return jsonify({"type": "error", "content": "Rate limit reached. Please try again later."})
    except OpenAIError as err:
        return jsonify({"type": "error", "content": f"API error: {err}"})

    reply = response.choices[0].message.content or ""
    _messages.append({"role": "assistant", "content": reply})
    return jsonify({"type": "text", "content": reply})


@app.route("/api/reset", methods=["POST"])
def reset():
    global _messages, _pending_location
    _messages = []
    _pending_location = False
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
