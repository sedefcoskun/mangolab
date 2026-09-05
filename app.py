from __future__ import annotations

import os
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse


app = FastAPI(title="fx-tool", version="1.0")

DEFAULT_UPSTREAM_BASE = "https://api.frankfurter.dev"
CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}

UPSTREAM_TIMEOUT = 5.0


def get_upstream_base() -> str:
    return os.getenv("FX_UPSTREAM_BASE", DEFAULT_UPSTREAM_BASE).rstrip("/")


def error_response(
    status_code: int,
    error: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "message": message,
        },
    )


async def fetch_rate(
    from_currency: str,
    to_currency: str,
    asked_date: str,
) -> dict[str, Any]:
    cache_key = (from_currency, to_currency, asked_date)

    if cache_key in CACHE:
        return CACHE[cache_key]

    url = f"{get_upstream_base()}/v1/{asked_date}"

    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
            response = await client.get(
                url,
                params={
                    "base": from_currency,
                    "symbols": to_currency,
                },
            )
    except httpx.TimeoutException:
        raise RuntimeError("upstream_timeout")
    except httpx.RequestError:
        raise RuntimeError("upstream_unavailable")

    if response.status_code == 404:
        raise RuntimeError("rate_not_available")

    if response.status_code >= 400:
        raise RuntimeError("upstream_error")

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("invalid_upstream")

    if not isinstance(data, dict):
        raise RuntimeError("invalid_upstream")

    rate_date = data.get("date")
    rates = data.get("rates")

    if not isinstance(rate_date, str) or not isinstance(rates, dict):
        raise RuntimeError("invalid_upstream")

    raw_rate = rates.get(to_currency)

    if raw_rate is None:
        raise RuntimeError("rate_not_available")

    try:
        rate = Decimal(str(raw_rate))
    except (InvalidOperation, ValueError):
        raise RuntimeError("invalid_upstream")

    if not rate.is_finite() or rate <= 0:
        raise RuntimeError("invalid_upstream")

    result = {
        "rate": rate,
        "rate_date": rate_date,
    }

    CACHE[cache_key] = result
    return result


@app.get("/tools/convert")
async def convert(
    amount: str | None = Query(default=None),
    from_currency: str | None = Query(default=None, alias="from"),
    to_currency: str | None = Query(default=None, alias="to"),
    requested_date: str | None = Query(default=None, alias="date"),
):
    if amount is None:
        return error_response(
            400,
            "missing_amount",
            "The amount parameter is required.",
        )

    try:
        decimal_amount = Decimal(amount)
    except InvalidOperation:
        return error_response(
            400,
            "invalid_amount",
            "Amount must be a positive number.",
        )

    if not decimal_amount.is_finite() or decimal_amount <= 0:
        return error_response(
            400,
            "invalid_amount",
            "Amount must be greater than zero.",
        )

    decimal_places = max(0, -decimal_amount.as_tuple().exponent)

    if decimal_places >= 10:
        return error_response(
            400,
            "invalid_amount",
            "Amount may have at most nine decimal places.",
        )
    
    MAX_AMOUNT = Decimal("1e15")

    if decimal_amount >= MAX_AMOUNT:
        return error_response(
        400,
        "invalid_amount",
        "Amount is too large.",
    )

    if not from_currency or not to_currency:
        return error_response(
            400,
            "missing_currency",
            "Both from and to currency codes are required.",
        )

    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if (
        len(from_currency) != 3
        or not from_currency.isalpha()
        or len(to_currency) != 3
        or not to_currency.isalpha()
    ):
        return error_response(
            400,
            "invalid_currency",
            "Currency codes must be three letters.",
        )

    if from_currency == to_currency:
        return error_response(
            400,
            "same_currency",
            "The source and target currencies must be different.",
        )

    if not requested_date:
        return error_response(
            400,
            "missing_date",
            "The date parameter is required.",
        )

    try:
        asked_date = date.fromisoformat(requested_date)
    except ValueError:
        return error_response(
            400,
            "invalid_date",
            "Date must use YYYY-MM-DD format.",
        )

    if asked_date > date.today():
        return error_response(
            400,
            "future_date",
            "A future date cannot be requested.",
        )

    try:
        rate_data = await fetch_rate(
            from_currency,
            to_currency,
            asked_date.isoformat(),
        )
    except RuntimeError as exc:
        error_code = str(exc)

        messages = {
            "rate_not_available": "No ECB rate is available for the requested date.",
            "upstream_timeout": "The exchange-rate service did not respond in time.",
            "upstream_unavailable": "The exchange-rate service could not be reached.",
            "upstream_error": "The exchange-rate service returned an error.",
            "invalid_upstream": "The exchange-rate service returned invalid data.",
        }

        status_code = (
            404
            if error_code == "rate_not_available"
            else 502
        )

        return error_response(
            status_code,
            error_code,
            messages.get(
                error_code,
                "The exchange-rate service failed.",
            ),
        )

    rate = rate_data["rate"]
    rate_date = rate_data["rate_date"]

    result = (decimal_amount * rate).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return {
        "amount": float(decimal_amount),
        "from": from_currency,
        "to": to_currency,
        "rate": float(rate),
        "result": float(result),
        "rate_date": rate_date,
        "asked_date": asked_date.isoformat(),
        "source": "ECB via frankfurter.dev",
    }