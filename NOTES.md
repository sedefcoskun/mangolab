# Notes

## Decisions

The main decision was keeping `asked_date` and `rate_date` separate. `asked_date` is whatever the caller requested; `rate_date` is whatever date the upstream actually returned the rate for. When those two differ — mostly weekends and holidays, where the ECB hasn't published anything yet — I didn't want the response to make it look like the requested date's rate was used when it wasn't.

Rates are cached by `(from, to, asked_date)` so a repeated question doesn't hit the upstream again. `FX_UPSTREAM_BASE` is read from the environment rather than hardcoded, mainly so the tests (and the reviewers) can point the service at something else entirely.

Amount validation also caps the magnitude, not just the sign and decimal places — see "one thing the AI got wrong" below for why.

## With more time

I'd add a TTL or size limit to the cache (right now it just grows forever), structured logging around upstream failures, stricter checks on what the upstream's `date` field actually contains, and tests for the timeout/connection-failure paths specifically, since those are currently thinner than the validation tests. I'd also switch to a single shared `httpx.AsyncClient` instead of opening a new one per request.

## AI tools

I used ChatGPT to help structure the service and think through edge cases, and to draft the test suite. I ran the test suite against a fake upstream with no network access, then manually tested the running service against the real Frankfurter API, including a weekend request to verify that `rate_date` is kept separate from `asked_date`.

## One thing the AI got wrong

While testing edge cases, a very large `amount` (like `1e28`) made the rounding step fail with an unhandled exception instead of a clean error — Decimal's default precision is 28 digits, and the multiplication overflowed it. I added an explicit ceiling on amount so oversized values now return `invalid_amount` (400) instead of crashing.

