import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture(autouse=True)
def clear_cache():
    app.CACHE.clear()
    yield
    app.CACHE.clear()


def make_client(monkeypatch, handler):
    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params=None):
            return handler(url, params, FakeResponse)

    monkeypatch.setattr(app.httpx, "AsyncClient", FakeAsyncClient)
    return TestClient(app.app)


def test_success_same_day(monkeypatch):
    calls = []

    def handler(url, params, response):
        calls.append((url, params))
        return response(
            200,
            {
                "amount": 250,
                "base": "EUR",
                "date": "2026-08-28",
                "rates": {"TRY": 47.1234},
            },
        )

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "250",
            "from": "EUR",
            "to": "TRY",
            "date": "2026-08-28",
        },
    )

    assert result.status_code == 200
    data = result.json()

    assert data["amount"] == 250
    assert data["from"] == "EUR"
    assert data["to"] == "TRY"
    assert data["rate"] == 47.1234
    assert data["result"] == 11780.85
    assert data["rate_date"] == "2026-08-28"
    assert data["asked_date"] == "2026-08-28"


def test_upstream_rate_date_is_preserved(monkeypatch):
    def handler(url, params, response):
        return response(
            200,
            {
                "date": "2026-08-27",
                "rates": {"TRY": 47.0},
            },
        )

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "from": "EUR",
            "to": "TRY",
            "date": "2026-08-28",
        },
    )

    assert result.status_code == 200
    data = result.json()

    assert data["asked_date"] == "2026-08-28"
    assert data["rate_date"] == "2026-08-27"


def test_cache_does_not_call_upstream_twice(monkeypatch):
    calls = []

    def handler(url, params, response):
        calls.append(1)
        return response(
            200,
            {
                "date": "2026-08-28",
                "rates": {"TRY": 47.0},
            },
        )

    client = make_client(monkeypatch, handler)

    params = {
        "amount": "100",
        "from": "EUR",
        "to": "TRY",
        "date": "2026-08-28",
    }

    first = client.get("/tools/convert", params=params)
    second = client.get("/tools/convert", params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("params", "error"),
    [
        (
            {"from": "EUR", "to": "TRY", "date": "2026-08-28"},
            "missing_amount",
        ),
        (
            {
                "amount": "0",
                "from": "EUR",
                "to": "TRY",
                "date": "2026-08-28",
            },
            "invalid_amount",
        ),
        (
            {
                "amount": "-10",
                "from": "EUR",
                "to": "TRY",
                "date": "2026-08-28",
            },
            "invalid_amount",
        ),
        (
            {
                "amount": "1.1234567890",
                "from": "EUR",
                "to": "TRY",
                "date": "2026-08-28",
            },
            "invalid_amount",
        ),
        (
            {
                "amount": "100",
                "from": "EUR",
                "to": "EUR",
                "date": "2026-08-28",
            },
            "same_currency",
        ),
        (
            {
                "amount": "100",
                "from": "EU",
                "to": "TRY",
                "date": "2026-08-28",
            },
            "invalid_currency",
        ),
        (
            {
                "amount": "100",
                "from": "EUR",
                "to": "TRY",
                "date": "not-a-date",
            },
            "invalid_date",
        ),
    ],
)
def test_validation_errors(monkeypatch, params, error):
    def handler(url, params, response):
        pytest.fail("Validation error must not call upstream")

    client = make_client(monkeypatch, handler)

    result = client.get("/tools/convert", params=params)

    assert result.status_code == 400
    assert result.json()["error"] == error


def test_missing_currency(monkeypatch):
    def handler(url, params, response):
        pytest.fail("Missing currency must not call upstream")

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "date": "2026-08-28",
        },
    )

    assert result.status_code == 400
    assert result.json()["error"] == "missing_currency"


def test_future_date(monkeypatch):
    def handler(url, params, response):
        pytest.fail("Future date must not call upstream")

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "from": "EUR",
            "to": "TRY",
            "date": "2999-01-01",
        },
    )

    assert result.status_code == 400
    assert result.json()["error"] == "future_date"


def test_rate_not_available(monkeypatch):
    def handler(url, params, response):
        return response(404, {"error": "not_found"})

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "from": "EUR",
            "to": "TRY",
            "date": "2026-08-30",
        },
    )

    assert result.status_code == 404
    assert result.json()["error"] == "rate_not_available"


def test_upstream_500(monkeypatch):
    def handler(url, params, response):
        return response(500, {"error": "server_error"})

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "from": "EUR",
            "to": "TRY",
            "date": "2026-08-28",
        },
    )

    assert result.status_code == 502
    assert result.json()["error"] == "upstream_error"


def test_invalid_upstream_json(monkeypatch):
    class BadResponse:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, params=None):
            return BadResponse()

    monkeypatch.setattr(app.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(app.app)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "from": "EUR",
            "to": "TRY",
            "date": "2026-08-28",
        },
    )

    assert result.status_code == 502
    assert result.json()["error"] == "invalid_upstream"


def test_missing_rate_in_upstream(monkeypatch):
    def handler(url, params, response):
        return response(
            200,
            {
                "date": "2026-08-28",
                "rates": {},
            },
        )

    client = make_client(monkeypatch, handler)

    result = client.get(
        "/tools/convert",
        params={
            "amount": "100",
            "from": "EUR",
            "to": "TRY",
            "date": "2026-08-28",
        },
    )

    assert result.status_code == 404
    assert result.json()["error"] == "rate_not_available"

