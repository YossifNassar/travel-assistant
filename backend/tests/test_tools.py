"""Tests for external API tools (get_weather, get_country_info, get_exchange_rate, get_public_holidays)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tools import get_country_info, get_exchange_rate, get_public_holidays, get_weather


def _make_async_client(mock_response):
    """Build a mock httpx.AsyncClient context manager that returns mock_response on .get()."""
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock()
    mock_cls.return_value = mock_client
    return mock_cls


def _make_sequential_client(*responses):
    """Build a mock that returns different responses on successive .get() calls."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = list(responses)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock()
    mock_cls.return_value = mock_client
    return mock_cls


# ---------------------------------------------------------------------------
# get_weather (Open-Meteo + Nominatim)
# ---------------------------------------------------------------------------
class TestGetWeather:
    @pytest.mark.asyncio
    async def test_successful_weather_response(self):
        geo_response = MagicMock()
        geo_response.json.return_value = [
            {"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France"}
        ]
        geo_response.raise_for_status.return_value = None

        weather_response = MagicMock()
        weather_response.json.return_value = {
            "current": {
                "temperature_2m": 18.5,
                "apparent_temperature": 17.2,
                "relative_humidity_2m": 55,
                "weather_code": 0,
                "wind_speed_10m": 12.0,
            },
            "daily": {
                "time": ["2026-02-15", "2026-02-16"],
                "temperature_2m_max": [20.0, 19.0],
                "temperature_2m_min": [12.0, 11.0],
                "precipitation_sum": [0.0, 2.5],
                "weather_code": [0, 61],
            },
        }
        weather_response.raise_for_status.return_value = None

        with patch("app.tools.httpx.AsyncClient", _make_sequential_client(geo_response, weather_response)):
            result = await get_weather.ainvoke({"city": "Paris"})

        assert "Paris" in result
        assert "18.5" in result
        assert "Clear sky" in result
        assert "7-day forecast" in result

    @pytest.mark.asyncio
    async def test_city_not_found(self):
        geo_response = MagicMock()
        geo_response.json.return_value = []
        geo_response.raise_for_status.return_value = None

        with patch("app.tools.httpx.AsyncClient", _make_async_client(geo_response)):
            result = await get_weather.ainvoke({"city": "Nonexistentcity"})

        assert "could not find" in result.lower()

    @pytest.mark.asyncio
    async def test_network_error_graceful(self):
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Network down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_cls = MagicMock()
        mock_cls.return_value = mock_client

        with patch("app.tools.httpx.AsyncClient", mock_cls):
            result = await get_weather.ainvoke({"city": "Paris"})

        assert "unavailable" in result.lower()


# ---------------------------------------------------------------------------
# get_country_info (RestCountries)
# ---------------------------------------------------------------------------
class TestGetCountryInfo:
    @pytest.mark.asyncio
    async def test_successful_country_response(self):
        mock_json = [
            {
                "name": {"official": "French Republic"},
                "capital": ["Paris"],
                "region": "Europe",
                "subregion": "Western Europe",
                "currencies": {"EUR": {"name": "Euro", "symbol": "\u20ac"}},
                "languages": {"fra": "French"},
                "population": 67390000,
                "timezones": ["UTC+01:00"],
            }
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status.return_value = None

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_country_info.ainvoke({"country_name": "France"})

        assert "French Republic" in result
        assert "Paris" in result
        assert "Euro" in result
        assert "French" in result
        assert "67.4 million" in result

    @pytest.mark.asyncio
    async def test_country_not_found_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_country_info.ainvoke({"country_name": "Narnia"})

        assert "could not find" in result.lower()

    @pytest.mark.asyncio
    async def test_network_error_graceful(self):
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Network down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_cls = MagicMock()
        mock_cls.return_value = mock_client

        with patch("app.tools.httpx.AsyncClient", mock_cls):
            result = await get_country_info.ainvoke({"country_name": "Japan"})

        assert "unavailable" in result.lower()


# ---------------------------------------------------------------------------
# get_exchange_rate (Frankfurter)
# ---------------------------------------------------------------------------
class TestGetExchangeRate:
    @pytest.mark.asyncio
    async def test_successful_conversion(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "amount": 100.0,
            "base": "USD",
            "date": "2026-02-15",
            "rates": {"JPY": 15023.45},
        }
        mock_response.raise_for_status.return_value = None

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_exchange_rate.ainvoke(
                {"from_currency": "USD", "to_currency": "JPY", "amount": 100.0}
            )

        assert "USD" in result
        assert "JPY" in result
        assert "15023.45" in result

    @pytest.mark.asyncio
    async def test_invalid_currency_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_exchange_rate.ainvoke(
                {"from_currency": "XYZ", "to_currency": "ABC"}
            )

        assert "not recognized" in result.lower()

    @pytest.mark.asyncio
    async def test_network_error_graceful(self):
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Network down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_cls = MagicMock()
        mock_cls.return_value = mock_client

        with patch("app.tools.httpx.AsyncClient", mock_cls):
            result = await get_exchange_rate.ainvoke(
                {"from_currency": "USD", "to_currency": "EUR"}
            )

        assert "unavailable" in result.lower()


# ---------------------------------------------------------------------------
# get_public_holidays (Nager.Date)
# ---------------------------------------------------------------------------
class TestGetPublicHolidays:
    @pytest.mark.asyncio
    async def test_successful_holidays(self):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-01-01", "localName": "Año Nuevo", "name": "New Year's Day"},
            {"date": "2026-01-06", "localName": "Día de Reyes", "name": "Epiphany"},
        ]
        mock_response.raise_for_status.return_value = None

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_public_holidays.ainvoke(
                {"country_code": "ES", "year": 2026}
            )

        assert "Año Nuevo" in result
        assert "New Year" in result
        assert "2026-01-01" in result
        assert "Día de Reyes" in result

    @pytest.mark.asyncio
    async def test_invalid_country_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_public_holidays.ainvoke(
                {"country_code": "XX", "year": 2026}
            )

        assert "could not find" in result.lower()

    @pytest.mark.asyncio
    async def test_network_error_graceful(self):
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Network down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_cls = MagicMock()
        mock_cls.return_value = mock_client

        with patch("app.tools.httpx.AsyncClient", mock_cls):
            result = await get_public_holidays.ainvoke(
                {"country_code": "JP", "year": 2026}
            )

        assert "unavailable" in result.lower()
