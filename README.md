# MangoLab FX Conversion Service

Small FastAPI service for converting currency amounts using ECB exchange rates through Frankfurter.

## Run

Requirements: Python 3.11+

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the service:

```bash
./run.sh
```

The default port is `8080`. It can be changed with:

```bash
PORT=9000 ./run.sh
```

## Endpoint

```text
GET /tools/convert
```

Example:

```text
/tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28
```

The response contains:

* `amount` — requested amount
* `from` — source currency
* `to` — target currency
* `rate` — exchange rate used
* `result` — converted amount
* `rate_date` — date the returned rate actually belongs to
* `asked_date` — date requested by the caller
* `source` — data source

`rate_date` is taken directly from the upstream response. This is important because the requested date may be a weekend or holiday, in which case the upstream can return the latest available rate. The service does not pretend that an older rate belongs to the requested date.

## Configuration

The upstream base URL is configured with:

```text
FX_UPSTREAM_BASE
```

Default:

```text
https://api.frankfurter.dev
```

The application does not hardcode the upstream host in request logic. This allows tests to point the service at a fake upstream.

The service port is configured with:

```text
PORT
```

Default:

```text
8080
```

## Tests

Run:

```bash
./test.sh
```

or:

```bash
python -m pytest -q
```

The tests do not require network access. The upstream HTTP client is replaced with a fake client.

The test suite covers successful conversion, caching, date handling, input validation, unavailable rates, upstream errors, and invalid upstream responses.

## Error codes

| HTTP | Error code             | Meaning                                                         |
| ---- | ---------------------- | --------------------------------------------------------------- |
| 400  | `missing_amount`       | Amount was not provided                                         |
| 400  | `invalid_amount`       | Amount is invalid, has too many decimal places, or is too large |
| 400  | `missing_currency`     | A currency parameter is missing                                 |
| 400  | `invalid_currency`     | Currency code is not three letters                              |
| 400  | `same_currency`        | Source and target currencies are identical                      |
| 400  | `missing_date`         | Date was not provided                                           |
| 400  | `invalid_date`         | Date is not valid `YYYY-MM-DD`                                  |
| 400  | `future_date`          | Requested date is in the future                                 |
| 404  | `rate_not_available`   | No rate is available for the requested date/currency pair       |
| 502  | `upstream_timeout`     | Upstream did not respond within the timeout                     |
| 502  | `upstream_unavailable` | Upstream could not be reached                                   |
| 502  | `upstream_error`       | Upstream returned an HTTP error                                 |
| 502  | `invalid_upstream`     | Upstream returned invalid or unusable data                      |

## Caching

Successful rate responses are cached by:

```text
(from, to, asked_date)
```

Repeating the same question does not call the upstream again.

## Project structure

```text
app.py                 FastAPI service
tests/test_app.py      Automated tests
run.sh                 Service startup script
test.sh                Test runner
requirements.txt       Python dependencies
NOTES.md               Implementation notes
REVIEW.md              Part B review
tool.py                Part B review target
```
