# Usage Metering & Billing Engine

A backend service that meters usage, enforces plan quotas, calculates cost (including AI-token
pricing rules), and syncs subscription state via signed, deduplicated payment-provider webhooks.
Built for the FlyRank Internship capstone.

> **Payment provider note:** this uses **Razorpay** instead of Stripe. Stripe requires an
> invite to sign up from India; FlyRank confirmed an alternative provider is acceptable. See
> `BUILDLOG.md` for details. Every requirement in the brief (signed webhooks, test mode, no
> real money, checkout → webhook → plan sync) is implemented the same way, just against
> Razorpay's API instead of Stripe's.

## Architecture

```
Client ─► POST /generate (idempotency_key, usage_type, quantity)
   └─► duplicate key? → return original result, no new row written
   └─► quota check → 200 recorded / 429 quota exceeded
   └─► usage_event row written

GET /usage/{tenant_id} ─► rollup(usage_events) → { used, limit, cost } per usage type

POST /checkout ─► creates Razorpay order (tenant_id stamped into order notes)
   └─► /checkout-page → browser-based Razorpay Checkout widget → real test-mode payment

Razorpay ─signed webhook─► POST /webhooks/razorpay
   ├─► verify HMAC-SHA256 signature (forged → 400)
   ├─► deduplicate by event id (replay → ignored)
   └─► update tenant's subscription plan
```

**Layers:**
```
HTTP layer (FastAPI routes in main.py)
    -> validates request shape, returns clean 4xx on bad input
Pricing logic (app/pricing.py)
    -> per-category token pricing, pinned and unit-tested independently of the API
Data layer (app/models.py + Postgres via SQLAlchemy)
    -> tenants, plans, subscriptions, usage_events, processed_webhook_events
```

Money is stored and calculated in integer cents throughout — never floats.

## How to run it

1. `docker compose up -d` — starts Postgres
2. `python -m venv venv` then activate it (`.\venv\Scripts\Activate.ps1` on Windows, `source venv/Scripts/activate` in Git Bash)
3. `pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv pydantic razorpay pytest`
4. Copy `.env.example` to `.env` and fill in your own Razorpay test-mode keys (get them free at razorpay.com, no card required)
5. `python create_tables.py` — creates the schema
6. `python seed.py` — creates two plans (free/pro) and a test tenant, prints the tenant id
7. `uvicorn main:app --reload` — starts the API on `http://localhost:8000`
8. `pytest test_pricing.py -v` — runs the pinned pricing tests

To test the full Razorpay checkout/webhook flow locally, you'll also need `ngrok http 8000` to
expose your local server publicly, and a webhook configured in the Razorpay test-mode dashboard
pointing at `<your-ngrok-url>/webhooks/razorpay`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /generate | Record billable usage. Idempotent by `idempotency_key`. Returns 429 if over quota. |
| GET | /usage/{tenant_id} | Usage, quota, and cost rollup for a tenant. |
| POST | /checkout | Creates a Razorpay order for upgrading to Pro. |
| GET | /checkout-page | Browser page with the Razorpay Checkout widget embedded. |
| POST | /webhooks/razorpay | Receives and verifies Razorpay webhook events, syncs plan state. |

## Example request

```
$ curl -i -X POST http://localhost:8000/generate -H "Content-Type: application/json" -d '{"tenant_id": 2, "usage_type": "api_call", "quantity": 5, "idempotency_key": "test-key-001"}'

HTTP/1.1 200 OK
content-type: application/json

{"status":"recorded","usage_event_id":1,"tenant_id":2,"type":"api_call","quantity":5,"usage_after":5,"quota":1000}
```

## Limitations

- No date/billing-period filtering yet — usage rollups are lifetime totals, not "this calendar month." Every tenant is effectively new for this capstone's scope.
- `ProcessedWebhookEvent`'s column is still named `stripe_event_id` internally (a naming leftover from the original Stripe-based design) even though it now stores Razorpay event ids. Functionally correct, cosmetically inconsistent.
- No invoicing, proration, or overage billing — explicitly out of scope per the brief.
- The Pro plan price (₹499) is hardcoded rather than configurable per plan.