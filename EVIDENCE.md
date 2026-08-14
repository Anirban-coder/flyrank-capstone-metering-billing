# Evidence

One proof per Definition of Done checkbox, pasted directly from actual runs.

## Metering

### A billable action creates exactly one usage event, even under retries — deduplicated by idempotency key.

```
$ curl -i -X POST http://localhost:8000/generate -d '{"tenant_id": 2, "usage_type": "api_call", "quantity": 5, "idempotency_key": "test-key-001"}'
HTTP/1.1 200 OK
{"status":"recorded","usage_event_id":1,"tenant_id":2,"type":"api_call","quantity":5,"usage_after":5,"quota":1000}

$ curl -i -X POST http://localhost:8000/generate -d '{"tenant_id": 2, "usage_type": "api_call", "quantity": 5, "idempotency_key": "test-key-001"}'
HTTP/1.1 200 OK
{"status":"duplicate_ignored","usage_event_id":1,"tenant_id":2,"type":"api_call","quantity":5}
```

### A test proves double-counting cannot happen.

Direct database check after sending the same key twice — exactly one row exists:

```
$ docker exec -it flyrank-capstone-metering-billing-db-1 psql -U postgres -d billing -c "SELECT * FROM usage_events WHERE idempotency_key='test-key-001';"
 id | tenant_id |   type   | quantity | idempotency_key |          created_at           | token_category
----+-----------+----------+----------+-----------------+-------------------------------+----------------
  1 |         2 | api_call |        5 | test-key-001    | 2026-08-12 17:58:34.028035+00 |
(1 row)
```

## Quotas

### Usage is checked against the tenant's plan; requests over the limit are rejected, with correct status codes and clear messages.

Exact-boundary test — free plan's limit is 1,000 API calls, tenant already had 5 recorded:

```
$ curl -i -X POST http://localhost:8000/generate -d '{"tenant_id": 2, "usage_type": "api_call", "quantity": 995, "idempotency_key": "test-key-003"}'
HTTP/1.1 200 OK
{"status":"recorded","usage_event_id":2,"tenant_id":2,"type":"api_call","quantity":995,"usage_after":1000,"quota":1000}

$ curl -i -X POST http://localhost:8000/generate -d '{"tenant_id": 2, "usage_type": "api_call", "quantity": 1, "idempotency_key": "test-key-004"}'
HTTP/1.1 429 Too Many Requests
{"detail":"Quota exceeded: 1000/1000 used, this request needs 1 more"}
```

Landing exactly at the limit succeeds; one unit over is rejected with `429` and an explanatory message.

## Cost calculation

### Monthly usage rolls up into a cost figure per tenant. AI token pricing handles cached input tokens, reasoning tokens, and output pricing correctly. Pricing constants are pinned and covered by tests.

Pinned test suite (`test_pricing.py`), all passing:

```
$ pytest test_pricing.py -v
test_pricing.py::test_input_token_cost PASSED
test_pricing.py::test_cached_input_is_cheaper_than_input PASSED
test_pricing.py::test_reasoning_tokens_billed_as_output PASSED
test_pricing.py::test_categories_priced_separately_not_summed_then_priced PASSED
test_pricing.py::test_full_mixed_usage_total PASSED
test_pricing.py::test_api_call_cost PASSED
test_pricing.py::test_unknown_category_raises PASSED
======= 7 passed in 0.07s =======
```

Live verification — sent real requests matching the pinned test's exact quantities, then checked the rollup endpoint returns the same number the unit test expects (230 cents):

```
$ curl -i http://localhost:8000/usage/2
{"tenant_id":2,"plan":"pro","api_calls":{"used":1000,"limit":10000,"cost_cents":1000},
 "ai_tokens":{"used":850000,"limit":1000000,
   "by_category":{"input":500000,"cached_input":200000,"output":100000,"reasoning":50000},
   "cost_cents":230},
 "total_cost_cents":1230}
```

## Stripe (Razorpay) integration

> Note: Stripe requires an invite to sign up from India and self-service signup is unavailable.
> FlyRank confirmed publicly (in response to another intern with the same restriction) that an
> alternative payment provider is acceptable. Razorpay was used instead — same shape of
> requirements: test mode with no card required, signed webhooks, checkout flow, subscription
> sync. See BUILDLOG.md for the full explanation.

### Subscription checkout works end-to-end in test mode.

`POST /checkout` created a real Razorpay test-mode order; the returned checkout page was opened
in a browser and a real test-mode payment was completed via net banking (card test numbers were
rejected by the account as "international"; net banking succeeded).

### Webhooks verify signatures, ignore duplicate events, and update tenant plan/status.

Real webhook, triggered by the actual test payment above, logged 200 OK in both the FastAPI
server and the ngrok tunnel. Database confirms the plan flipped:

```
$ docker exec -it flyrank-capstone-metering-billing-db-1 psql -U postgres -d billing \
  -c "SELECT s.tenant_id, p.name, s.status FROM subscriptions s JOIN plans p ON s.plan_id=p.id WHERE s.tenant_id=2;"
 tenant_id | name | status
-----------+------+--------
         2 | pro  | active
(1 row)
```

Forged signature rejected:
```
$ curl -i -X POST http://localhost:8000/webhooks/razorpay -H "X-Razorpay-Signature: totally-fake-signature" -d '...'
HTTP/1.1 400 Bad Request
{"detail":"Invalid webhook signature"}
```

Duplicate (replayed) event ignored, via `test_webhook_replay.py` (constructs a correctly-signed
payload and sends it twice with the same event id):
```
First send (should be 'processed'):
200 {"status":"processed"}
Second send, same event id (should be 'duplicate_ignored'):
200 {"status":"duplicate_ignored"}
```

## Data model, tests & documentation

Database includes tenants, plans, subscriptions, usage_events, and processed_webhook_events
(see DESIGN.md for full schema). Tests cover: duplicate usage prevention (above), quota boundary
cases (above), cost calculations (`test_pricing.py`), invalid-webhook rejection (above), and
duplicate-webhook handling (above).