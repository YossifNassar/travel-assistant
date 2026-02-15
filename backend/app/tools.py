"""External API tools for the Travel Assistant agent.

Provides weather data (OpenWeatherMap) and country information (RestCountries)
that the agent can invoke to augment its responses with real-time data.
"""

import os
import httpx
from langchain_core.tools import tool


@tool
async def get_weather(city: str, country_code: str = "") -> str:
    """Get current weather for a city. Use this when the user asks about
    weather conditions, what to pack, what to wear, or when planning
    activities that depend on weather. Provide the city name and optionally
    a 2-letter country code (e.g. 'US', 'FR', 'JP') to disambiguate.

    Args:
        city: Name of the city (e.g. 'Paris', 'Tokyo', 'New York')
        country_code: Optional ISO 3166-1 alpha-2 country code
    """
    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key:
        return (
            "Weather data is temporarily unavailable (API key not configured). "
            "I'll provide general climate guidance based on my knowledge instead."
        )

    query = f"{city},{country_code}" if country_code else city
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": query, "appid": api_key, "units": "metric"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        weather = data["weather"][0]
        main = data["main"]
        wind = data["wind"]

        return (
            f"Current weather in {data['name']}, {data.get('sys', {}).get('country', '')}:\n"
            f"- Conditions: {weather['description'].title()}\n"
            f"- Temperature: {main['temp']}°C (feels like {main['feels_like']}°C)\n"
            f"- High/Low: {main['temp_max']}°C / {main['temp_min']}°C\n"
            f"- Humidity: {main['humidity']}%\n"
            f"- Wind: {wind['speed']} m/s"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Could not find weather data for '{city}'. Please check the city name and try again."
        return f"Weather service error (HTTP {e.response.status_code}). I'll use my general knowledge instead."
    except Exception:
        return "Weather service is temporarily unavailable. I'll provide general climate guidance instead."


@tool
async def get_country_info(country_name: str) -> str:
    """Get essential travel information about a country. Use this when the
    user asks about a destination's currency, language, capital, population,
    or general country-level facts useful for trip planning.

    Args:
        country_name: Full name of the country (e.g. 'Japan', 'France', 'Brazil')
    """
    url = f"https://restcountries.com/v3.1/name/{country_name}"
    params = {"fields": "name,capital,currencies,languages,population,region,subregion,timezones,flags"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if not data:
            return f"No information found for '{country_name}'."

        # Use the first (best) match
        country = data[0]

        official_name = country.get("name", {}).get("official", country_name)
        capital = ", ".join(country.get("capital", ["Unknown"]))
        region = country.get("region", "Unknown")
        subregion = country.get("subregion", "")

        # Format currencies
        currencies = country.get("currencies", {})
        currency_parts = []
        for code, info in currencies.items():
            symbol = info.get("symbol", "")
            name = info.get("name", code)
            currency_parts.append(f"{name} ({code}) {symbol}".strip())
        currency_str = ", ".join(currency_parts) if currency_parts else "Unknown"

        # Format languages
        languages = country.get("languages", {})
        language_str = ", ".join(languages.values()) if languages else "Unknown"

        # Format population
        pop = country.get("population", 0)
        if pop >= 1_000_000:
            pop_str = f"{pop / 1_000_000:.1f} million"
        elif pop >= 1_000:
            pop_str = f"{pop / 1_000:.1f} thousand"
        else:
            pop_str = str(pop)

        # Timezones
        timezones = ", ".join(country.get("timezones", ["Unknown"]))

        return (
            f"Country: {official_name}\n"
            f"- Capital: {capital}\n"
            f"- Region: {region}{f' ({subregion})' if subregion else ''}\n"
            f"- Currency: {currency_str}\n"
            f"- Languages: {language_str}\n"
            f"- Population: {pop_str}\n"
            f"- Timezones: {timezones}"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Could not find information for '{country_name}'. Please check the country name."
        return f"Country info service error. I'll use my general knowledge instead."
    except Exception:
        return "Country info service is temporarily unavailable. I'll use my general knowledge instead."
