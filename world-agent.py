import os
import json
import re
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openai import AuthenticationError, OpenAI, OpenAIError, RateLimitError


def load_env_file(path: str = "key.env") -> None:
    """Load simple KEY=value lines into os.environ."""
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"Could not find {path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :]

        key, separator, value = line.partition("=")
        if not separator:
            continue

        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "world-agent/0.1"})

    with urlopen(request, timeout=15) as response:
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
        marker_index = lower_text.rfind(marker)
        if marker_index != -1:
            return clean_location_query(text[marker_index + len(marker) :])

    return ""


def split_locations(location_text: str) -> list[str]:
    normalized = clean_location_query(location_text)
    normalized = re.sub(r"\s+(and|&)\s+", ",", normalized, flags=re.IGNORECASE)
    parts = re.split(r"[,;]+", normalized)

    return [clean_location_query(part) for part in parts if clean_location_query(part)]


def format_current_conditions(location: str) -> str:
    weather_agent = WeatherSubAgent()
    time_agent = TimeSubAgent()

    try:
        weather = weather_agent.run(location)
        time_info = {
            "current_time": weather.get("current_time"),
            "timezone": weather.get("timezone"),
        }
        if not time_info["current_time"]:
            time_info = time_agent.run(weather["latitude"], weather["longitude"])
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as error:
        return f"I could not retrieve current online data for {location}: {error}"

    return (
        f"Current data for {weather['location'] or location}:\n"
        f"- Temperature: {weather['temperature_c']} C / {weather['temperature_f']} F\n"
        f"- Time: {time_info['current_time']} ({time_info['timezone']})\n"
        f"- Weather type: {weather['weather_type']}\n"
        f"- Humidity: {weather['humidity_percent']}%"
    )


def format_current_conditions_for_locations(location_text: str) -> str:
    locations = split_locations(location_text)

    if not locations:
        return "Please tell me which city or location to check."

    reports = [format_current_conditions(location) for location in locations]

    return "\n\n".join(reports)


def main() -> None:
    load_env_file()

    client = OpenAI(
        api_key=os.environ["PARALLEL_API_KEY"],
        base_url="https://api.parallel.ai",
    )

    messages = [
        {
            "role": "system",
            "content": "You are my first world agent. Be concise, curious, and helpful.",
        }
    ]
    pending_current_conditions_location = False

    print("World Agent is ready. Type 'exit' or 'quit' to end the session.")

    while True:
        user_message = input("\nYou: ").strip()

        if user_message.lower() in {"exit", "quit"}:
            print("Agent: Goodbye.")
            break

        if not user_message:
            continue

        if pending_current_conditions_location:
            location = user_message
            pending_current_conditions_location = False
            agent_message = format_current_conditions_for_locations(location)
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": agent_message})
            print(f"Agent: {agent_message}")
            continue

        if is_current_conditions_request(user_message):
            location = extract_location(user_message)

            if not location:
                pending_current_conditions_location = True
                agent_message = "Which city or location should I check right now?"
                messages.append({"role": "user", "content": user_message})
                messages.append({"role": "assistant", "content": agent_message})
                print(f"Agent: {agent_message}")
                continue

            agent_message = format_current_conditions_for_locations(location)
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": agent_message})
            print(f"Agent: {agent_message}")
            continue

        messages.append({"role": "user", "content": user_message})

        try:
            response = client.chat.completions.create(
                model="speed",
                messages=messages,
            )
        except AuthenticationError:
            print("Agent: Parallel rejected the API key. Check PARALLEL_API_KEY in key.env.")
            return
        except RateLimitError:
            print("Agent: The account has no available quota or hit a rate limit.")
            return
        except OpenAIError as error:
            print(f"Agent: Parallel API error: {error}")
            return

        agent_message = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": agent_message})

        print(f"Agent: {agent_message}")


if __name__ == "__main__":
    main()
