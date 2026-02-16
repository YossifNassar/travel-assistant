"""External API tools for the Travel Assistant agent.

All tools use free APIs that require NO API keys:
- Open-Meteo + Nominatim: weather forecasts (replaces OpenWeatherMap)
- RestCountries: country information
- Frankfurter: currency exchange rates
- Nager.Date: public holidays
"""

import httpx
from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Weather (Open-Meteo + Nominatim geocoding — no API key needed)
# ---------------------------------------------------------------------------
@tool
async def get_weather(city: str, country_code: str = "") -> str:
    """Get current weather and a 7-day forecast for a city. Use this when the
    user asks about weather conditions, what to pack, what to wear, or when
    planning activities that depend on weather.

    Args:
        city: Name of the city (e.g. 'Paris', 'Tokyo', 'New York')
        country_code: Optional ISO 3166-1 alpha-2 country code to disambiguate
    """
    try:
        # Step 1: Geocode the city name to lat/lon via Nominatim
        query = f"{city}, {country_code}" if country_code else city
        async with httpx.AsyncClient(timeout=10.0) as client:
            geo_resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "TravelAssistant/1.0"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()

        if not geo_data:
            return f"Could not find location '{city}'. Please check the city name and try again."

        lat = float(geo_data[0]["lat"])
        lon = float(geo_data[0]["lon"])
        display_name = geo_data[0].get("display_name", city)

        # Step 2: Fetch weather from Open-Meteo
        async with httpx.AsyncClient(timeout=10.0) as client:
            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                    "timezone": "auto",
                    "forecast_days": 7,
                },
            )
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()

        current = weather_data.get("current", {})
        daily = weather_data.get("daily", {})

        # Decode WMO weather code to description
        condition = _wmo_code_to_text(current.get("weather_code", -1))

        lines = [
            f"Weather for {display_name.split(',')[0]} (lat {lat:.2f}, lon {lon:.2f}):",
            f"\nCurrent conditions:",
            f"- {condition}",
            f"- Temperature: {current.get('temperature_2m')}°C (feels like {current.get('apparent_temperature')}°C)",
            f"- Humidity: {current.get('relative_humidity_2m')}%",
            f"- Wind: {current.get('wind_speed_10m')} km/h",
            f"\n7-day forecast:",
        ]

        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        codes = daily.get("weather_code", [])

        for i in range(min(7, len(dates))):
            day_cond = _wmo_code_to_text(codes[i] if i < len(codes) else -1)
            rain = f", {precip[i]}mm rain" if i < len(precip) and precip[i] > 0 else ""
            lines.append(
                f"- {dates[i]}: {lows[i]}°C – {highs[i]}°C, {day_cond}{rain}"
            )

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Weather service error (HTTP {e.response.status_code}). I'll use my general knowledge instead."
    except Exception:
        return "Weather service is temporarily unavailable. I'll provide general climate guidance instead."


def _wmo_code_to_text(code: int) -> str:
    """Convert WMO weather interpretation code to human-readable text."""
    mapping = {
        0: "Clear sky",
        1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        85: "Slight snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
    }
    return mapping.get(code, "Unknown conditions")


# ---------------------------------------------------------------------------
# Country info (RestCountries — no API key needed)
# ---------------------------------------------------------------------------
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

        country = data[0]

        official_name = country.get("name", {}).get("official", country_name)
        capital = ", ".join(country.get("capital", ["Unknown"]))
        region = country.get("region", "Unknown")
        subregion = country.get("subregion", "")

        currencies = country.get("currencies", {})
        currency_parts = []
        for code, info in currencies.items():
            symbol = info.get("symbol", "")
            name = info.get("name", code)
            currency_parts.append(f"{name} ({code}) {symbol}".strip())
        currency_str = ", ".join(currency_parts) if currency_parts else "Unknown"

        languages = country.get("languages", {})
        language_str = ", ".join(languages.values()) if languages else "Unknown"

        pop = country.get("population", 0)
        if pop >= 1_000_000:
            pop_str = f"{pop / 1_000_000:.1f} million"
        elif pop >= 1_000:
            pop_str = f"{pop / 1_000:.1f} thousand"
        else:
            pop_str = str(pop)

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
        return "Country info service error. I'll use my general knowledge instead."
    except Exception:
        return "Country info service is temporarily unavailable. I'll use my general knowledge instead."


# ---------------------------------------------------------------------------
# Exchange rates (Frankfurter — no API key needed)
# ---------------------------------------------------------------------------
@tool
async def get_exchange_rate(from_currency: str, to_currency: str, amount: float = 1.0) -> str:
    """Convert between currencies using live exchange rates. Use this when the
    user asks about currency conversion, how much things cost in their home
    currency, or exchange rates for a destination.

    Args:
        from_currency: Source currency code (e.g. 'USD', 'EUR', 'GBP')
        to_currency: Target currency code (e.g. 'JPY', 'THB', 'MXN')
        amount: Amount to convert (default: 1.0)
    """
    url = "https://api.frankfurter.app/latest"
    params = {"from": from_currency.upper(), "to": to_currency.upper(), "amount": amount}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        rates = data.get("rates", {})
        if not rates:
            return f"Could not find exchange rate from {from_currency} to {to_currency}."

        target = to_currency.upper()
        converted = rates.get(target, 0)

        return (
            f"Exchange rate ({data.get('date', 'today')}):\n"
            f"- {amount} {from_currency.upper()} = {converted:.2f} {target}\n"
            f"- Rate: 1 {from_currency.upper()} = {converted / amount:.4f} {target}"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Currency code '{from_currency}' or '{to_currency}' not recognized. Use standard 3-letter ISO codes (e.g. USD, EUR, JPY)."
        return "Exchange rate service error. I'll use my general knowledge instead."
    except Exception:
        return "Exchange rate service is temporarily unavailable. I'll use my general knowledge instead."


# ---------------------------------------------------------------------------
# Public holidays (Nager.Date — no API key needed)
# ---------------------------------------------------------------------------
@tool
async def get_public_holidays(country_code: str, year: int = 2026) -> str:
    """Get public holidays for a country in a given year. Use this when the
    user asks about holidays, festivals, or wants to know if anything special
    is happening during their visit. This helps with trip planning around
    local celebrations or avoiding closures.

    Args:
        country_code: ISO 3166-1 alpha-2 country code (e.g. 'JP', 'FR', 'US', 'ES')
        year: Year to look up holidays for (default: 2026)
    """
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code.upper()}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if not data:
            return f"No public holidays found for country code '{country_code}' in {year}."

        lines = [f"Public holidays in {country_code.upper()} for {year}:\n"]
        for holiday in data:
            date = holiday.get("date", "")
            name = holiday.get("localName", holiday.get("name", "Unknown"))
            intl_name = holiday.get("name", "")
            if intl_name and intl_name != name:
                lines.append(f"- {date}: {name} ({intl_name})")
            else:
                lines.append(f"- {date}: {name}")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Could not find holidays for country code '{country_code}'. Use a 2-letter ISO code (e.g. 'JP', 'FR', 'US')."
        return "Holiday service error. I'll use my general knowledge instead."
    except Exception:
        return "Holiday service is temporarily unavailable. I'll use my general knowledge instead."
