# Review of `tool.py`

I reviewed `tool.py` as a customer-facing service. I focused mainly on cases where the service could return an incorrect conversion or make a failed request look successful.

## 1. Cache ignores the requested date

The cache key is only based on the source and target currencies:

`f"{base}-{target}"`

The requested date is not included. Therefore, two requests for the same currency pair but different dates can use the same cached rate.

This can return a rate from the wrong date to the customer.

**How I would check it:** use a fake upstream that returns different rates for two dates, then request both dates without restarting the service. The second request should not reuse the first rate.

## 2. `rate_date` can be wrong

`fetch_rate()` returns `str(on or date.today())` instead of using the `date` returned by the upstream service.

This is especially problematic for weekends and holidays. For example, I requested `2026-08-30`. The upstream returned a rate with `date: 2026-08-28`, but `tool.py` returned `rate_date: 2026-08-30`.

The customer therefore cannot reliably know which date the rate actually belongs to.

## 3. Upstream errors become successful `0.0` conversions

The broad `except Exception` catches all failures and returns a normal-looking response with `rate: 0.0` and `result: 0.0`.

This is risky because a failed conversion can look like a valid conversion to a customer or an agent.

**How I checked it:** requesting an invalid currency (`to=INVALID`) returned `rate: 0.0` and `result: 0.0` instead of a clear error response.

## 4. Negative amounts are accepted

There is no validation that the amount must be positive.

I tested `amount=-100` and the service returned a normal response with `result: -5617.0`.

A customer should receive a validation error instead of a negative conversion result.

## 5. Same source and target currencies are accepted

There is no check for `from == to`.

I tested EUR → EUR and the service returned a `0.0` result through the generic error handling.

This should be rejected clearly as invalid input rather than being presented as a failed conversion.

## 6. Future dates are accepted

There is no validation preventing a future date.

I tested `on=2030-01-01` and received a normal-looking conversion with `rate_date: 2030-01-01`.

A future date has no published ECB rate, so the service should reject it rather than returning a rate labelled with that date.

## 7. The upstream URL is hardcoded

The service always uses:

`https://api.frankfurter.dev/v1`

It does not read `FX_UPSTREAM_BASE`.

This makes it harder to run the service against a controlled upstream for testing, and it prevents the configuration required by the case from being used.

**How I would check it:** set `FX_UPSTREAM_BASE` to another URL and verify where the request is actually sent.

## 8. The exchange rate is rounded too early

The code does:

`rate = round(rate, 2)`

before calculating the result.

This loses precision from the original upstream rate. For example, the upstream returned `56.1718` for EUR → TRY, while the service used `56.17`. For 100 EUR this gives `5617.00` instead of `5617.18`.

The rate should keep its original precision and only the final conversion result should be rounded.

## The one I would fix before shipping tonight

I would fix the error handling first.

Returning `200` with `rate: 0.0` when the conversion failed is the biggest risk because it can make a service failure look like a valid customer result.

After that, I would fix the date-aware cache and `rate_date`, since these can produce incorrect historical rates.

## Things that look suspicious but are fine

The `/health` endpoint only returns `{"ok": True}` and does not check the upstream service. I would not consider this a bug by itself. For a health/liveness endpoint, checking that the application process is alive is reasonable; the conversion endpoint can handle upstream failures separately.

The in-process cache is also not inherently a problem for a small single-process service. The problem is the cache key and the information stored with the cached rate.

