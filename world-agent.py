import os
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
            "location": ", ".join(part for part in [area_name, region, country] if part),
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
        marker_index = lower_text.rfind(marker)
        if marker_index != -1:
            return text[marker_index + len(marker) :].strip(" ?.")

    return ""


def split_locations(location_text: str) -> list[str]:
    normalized = re.sub(r"\s+(and|&)\s+", ",", location_text, flags=re.IGNORECASE)
    parts = re.split(r"[,;]+", normalized)

    return [part.strip(" ?.") for part in parts if part.strip(" ?.")]


def format_current_conditions(location: str) -> str:
    weather_agent = WeatherSubAgent()
    time_agent = TimeSubAgent()

    try:
        weather = weather_agent.run(location)
        time_info = time_agent.run(weather["latitude"], weather["longitude"])
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
        return f"I could not retrieve current online data for {location}: {error}"

    return (
        f"Current data for {weather['location'] or location}:\n"
        f"- Temperature: {weather['temperature_c']} C / {weather['temperature_f']} F\n"
        f"- Time: {time_info['current_time']} ({time_info['timezone']})\n"
        f"- Weather type: {weather['weather_type']}\n"
        f"- Humidity: {weather['humidity_percent']}%\n"
        f"- Weather observation time: {weather['observation_time']}"
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
