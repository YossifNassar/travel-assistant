"""Tests for external API tools (get_weather, get_country_info)."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tools import get_weather, get_country_info


def _make_async_client(mock_response):
    """Build a mock httpx.AsyncClient context manager that returns mock_response on .get()."""
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock()
    mock_cls.return_value = mock_client
    return mock_cls


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------
class TestGetWeather:
    @pytest.mark.asyncio
    async def test_returns_fallback_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        monkeypatch.setattr(os, "getenv", lambda key, default="": "" if key == "OPENWEATHER_API_KEY" else default)

        result = await get_weather.ainvoke({"city": "Paris"})
        assert "unavailable" in result.lower() or "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_successful_weather_response(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")

        mock_json = {
            "name": "Paris",
            "sys": {"country": "FR"},
            "weather": [{"description": "clear sky"}],
            "main": {
                "temp": 18.5,
                "feels_like": 17.2,
                "temp_max": 20.0,
                "temp_min": 16.0,
                "humidity": 55,
            },
            "wind": {"speed": 3.5},
        }

        # Use MagicMock for response — httpx response methods are synchronous
        mock_response = MagicMock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status.return_value = None

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_weather.ainvoke({"city": "Paris"})

        assert "Paris" in result
        assert "18.5" in result
        assert "Clear Sky" in result

    @pytest.mark.asyncio
    async def test_city_not_found_404(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")

        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        with patch("app.tools.httpx.AsyncClient", _make_async_client(mock_response)):
            result = await get_weather.ainvoke({"city": "Nonexistentcity"})

        assert "could not find" in result.lower()

    @pytest.mark.asyncio
    async def test_network_error_graceful(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")

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
# get_country_info
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
