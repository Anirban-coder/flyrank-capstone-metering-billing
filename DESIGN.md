# Design Doc — Usage Metering & Billing Engine

## Problem

SaaS products need to answer three questions for every customer: how much have they used, what should
they be charged, and have they hit their plan's limit. This service meters usage per tenant, enforces
plan quotas before allowing billable actions, calculates cost from usage (including AI-token pricing
rules), and keeps subscription state in sync with Stripe via verified, deduplicated webhooks.

Core guarantee: a retried request never double-counts usage, and a quota boundary is enforced exactly
— not approximately.

## Data model

- **tenant** — id, name, created_at
- **plan** — id, name (`free` / `pro`), monthly_api_call_limit, monthly_token_limit
- **subscription** — id, tenant_id (FK), plan_id (FK), stripe_customer_id, stripe_subscription_id,
  status (`active` / `canceled` / etc.), current_period_start, current_period_end
- **usage_event** — id, tenant_id (FK), type (`api_call` / `ai_tokens`), quantity, idempotency_key
  (unique), created_at
- **processed_webhook_event** — stripe_event_id (unique, primary key), processed_at
  — exists purely so a replayed Stripe event is recognized and ignored, not reprocessed

Plans (fixed for this capstone):

| Plan | API calls / month | AI tokens / month |
|---|---|---|
| Free | 1,000 | 100,000 |
| Pro | 10,000 | 1,000,000 |

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | /generate | Dummy billable action. Body includes `idempotency_key`, usage type, quantity. Records a usage event (or returns the original result if the key was already used), checks quota, returns 200/402/429. |
| GET | /usage/{tenant_id} | Rollup: used, limit, cost for the current period, per usage type. |
| POST | /checkout | Creates a Stripe Checkout session for a tenant to subscribe to Pro. |
| POST | /webhooks/stripe | Receives Stripe events. Verifies signature, deduplicates by `stripe_event_id`, updates subscription/plan on `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`. |

## Layer sketch

```
HTTP layer (FastAPI routes)
    -> validates request shape, returns clean 4xx on bad input
Service layer (MeterService, QuotaService, BillingService, StripeWebhookService)
    -> all business rules: idempotency, quota math, cost math, webhook dedup
Data layer (SQLAlchemy models + Postgres)
    -> no business logic here, just persistence
```

Money is stored as integer cents/micro-units throughout — never floats — from the DB up through every
calculation.

## Non-goal

This capstone does not implement invoicing, proration, or overage billing in the core build. Those are
explicitly listed as stretch goals in the brief and are out of scope unless the core Definition of Done
is fully green first.
