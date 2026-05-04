# World Agent

World Agent is a small Flask web app with a main orchestrator agent and sub-agents that retrieve current city data from the internet.

It can chat normally through Parallel AI, and when the user asks for weather, time, temperature, or humidity, it delegates that request to live data sub-agents.

## Features

- Web chat interface at `http://127.0.0.1:5000`
- Main `OrchestratorAgent` that decides how to handle each message
- Sub-agents for current weather and time retrieval
- Multi-city requests, such as `weather in San Francisco, Tokyo and New York`
- Strict city matching to avoid false results from nearby locations
- Local API key loading from `key.env`

## Agent Architecture

The backend is organized around one main agent and several sub-agents:

- `OrchestratorAgent` - main decision maker. It decides whether to answer with the LLM or delegate to current-condition sub-agents.
- `CurrentConditionsAgent` - coordinates city condition retrieval for one or many cities.
- `WeatherSubAgent` - resolves the exact city and retrieves current temperature, weather type, humidity, coordinates, and timezone from Open-Meteo.
- `TimeSubAgent` - retrieves local time by coordinates when needed.

The orchestrator refuses fuzzy weather matches. For example, if the user asks for `San Francisco`, the weather card must resolve to `San Francisco`, not a nearby neighborhood or unrelated place.

## Project Files

- `app.py` - Flask backend, orchestrator, and sub-agent logic
- `static/index.html` - web app HTML
- `static/script.js` - browser chat logic
- `static/style.css` - app styling
- `world-agent.py` - optional terminal version of the agent
- `key.env` - local API key file, ignored by Git
- `requirements.txt` - Python dependencies

## Setup

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create `key.env` in the project root:

```bash
export PARALLEL_API_KEY=your_parallel_api_key_here
```

Do not commit `key.env`.

## Run The Web App

From the project folder:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Example Questions

```text
What is the weather in San Francisco?
```

```text
Get the temperature, time, weather type, and humidity in London, Tokyo, New York.
```

```text
What is the humidity in Mumbai and Singapore right now?
```

```text
Compare weather in Madrid, Paris and Rome.
```

## Optional Terminal Agent

You can also run the terminal version:

```powershell
.\.venv\Scripts\python.exe world-agent.py
```

Type `exit` or `quit` to end the terminal session.

## Data Sources

- Parallel AI for general chat through an OpenAI-compatible API
- Open-Meteo Geocoding API for city resolution
- Open-Meteo Forecast API for current weather data
- TimeAPI.io for current local time fallback by coordinates

## Troubleshooting

If you see:

```text
ModuleNotFoundError: No module named 'openai'
```

Run the app with the virtual environment Python:

```powershell
.\.venv\Scripts\python.exe app.py
```

If Flask reloads after file changes, that is normal because `app.py` runs with `debug=True`.

If a city lookup fails, use a clearer city name. The agent is designed to avoid false information, so it may ask for a more specific location instead of guessing.
