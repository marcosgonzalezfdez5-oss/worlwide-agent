# World Agent

A beginner Python agent that chats in the terminal and can retrieve current online weather and time data for one or more cities.

The project uses:

- Parallel AI through the OpenAI-compatible Python SDK
- `wttr.in` for current weather data
- `timeapi.io` for current local time by coordinates

## Features

- Keeps a chat session open until you type `exit` or `quit`
- Uses a `PARALLEL_API_KEY` from `key.env`
- Retrieves current temperature, local time, weather type, and humidity
- Supports multiple cities in one question

Example:

```text
You: weather in London, Tokyo, New York
Agent: Current data for London...
```

## Project Files

- `world-agent.py` - main terminal agent
- `key.env` - local API key file, ignored by Git
- `requirements.txt` - Python dependencies
- `.gitignore` - prevents secrets and virtual environments from being committed

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
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

## Run

From the project folder:

```powershell
.\.venv\Scripts\python.exe world-agent.py
```

Then chat with the agent:

```text
You: hello
You: weather in Paris
You: weather in London, Tokyo and New York
You: exit
```

## How It Works

The main agent reads your terminal input and keeps the conversation history in memory.

When your message asks for current conditions, it uses two small sub-agents:

- `WeatherSubAgent` calls `wttr.in` and retrieves temperature, weather type, humidity, and coordinates.
- `TimeSubAgent` uses the coordinates to call `timeapi.io` and retrieve current local time.

If your message does not look like a current weather or time request, the agent sends the message to Parallel AI.

## Example Questions

```text
What is the weather in Madrid?
```

```text
Get the temperature, time, weather type, and humidity in London, Tokyo, New York.
```

```text
What is the humidity in Mumbai and Singapore right now?
```

## Troubleshooting

If you see:

```text
ModuleNotFoundError: No module named 'openai'
```

Run the script with the virtual environment Python:

```powershell
.\.venv\Scripts\python.exe world-agent.py
```

If Parallel rejects the key, check that `key.env` contains:

```bash
export PARALLEL_API_KEY=your_parallel_api_key_here
```

If weather or time retrieval fails, check your internet connection and try again with a clearer city name.
