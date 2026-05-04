import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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


class WeatherSubAgent:
    def run(self, location: str) -> dict:
        url = f"https://wttr.in/{quote(location)}?format=j1"
        data = get_json(url)
        current = data["current_condition"][0]
        nearest_area = data.get("nearest_area", [{}])[0]
        area_name = self._first_value(nearest_area.get("areaName"))
        country = self._first_value(nearest_area.get("country"))
        region = self._first_value(nearest_area.get("region"))
        return {
            "location": ", ".join(p for p in [area_name, region, country] if p),
            "latitude": nearest_area.get("latitude"),
            "longitude": nearest_area.get("longitude"),
            "temperature_c": current.get("temp_C"),
            "temperature_f": current.get("temp_F"),
            "weather_type": self._first_value(current.get("weatherDesc")),
            "humidity_percent": current.get("humidity"),
            "observation_time": current.get("observation_time"),
        }

    @staticmethod
    def _first_value(values: list | None) -> str:
        if not values:
            return ""
        return values[0].get("value", "")


class TimeSubAgent:
    def run(self, latitude: str | None, longitude: str | None) -> dict:
        if not latitude or not longitude:
            return {"current_time": "Unavailable", "timezone": "Unavailable"}
        url = (
            "https://www.timeapi.io/api/Time/current/coordinate"
            f"?latitude={quote(latitude)}&longitude={quote(longitude)}"
        )
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
            return text[idx + len(marker):].strip(" ?.")
    return ""


def split_locations(location_text: str) -> list[str]:
    normalized = re.sub(r"\s+(and|&)\s+", ",", location_text, flags=re.IGNORECASE)
    parts = re.split(r"[,;]+", normalized)
    return [p.strip(" ?.") for p in parts if p.strip(" ?.")]


def get_weather_data(location_text: str) -> list[dict]:
    locations = split_locations(location_text)
    results = []
    weather_agent = WeatherSubAgent()
    time_agent = TimeSubAgent()
    for location in locations:
        try:
            weather = weather_agent.run(location)
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
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as err:
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
