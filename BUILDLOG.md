# Build Log

## Phase 1 — Design
- Used Claude to draft the initial DESIGN.md structure (data model, API surface, layer sketch)
- Reviewed and understood each table/endpoint before committing
- Chose Pro plan limits (10k calls / 1M tokens) myself
## Phase 2 — Environment debugging
- Docker Desktop install/PATH/engine issues took significant time to resolve (broken shortcut, PATH not set, engine not running)
- Worked through with Claude step by step; root cause each time before changing anything
## Phase 2 — Metering endpoint
- Built /generate with Claude: idempotency check first, then quota check, then record
- Tested: same idempotency_key twice → only one usage_event row (verified in DB directly)
- Tested boundary: exactly at quota succeeds, quota+1 rejected with 429
## Phase 3 — Payment provider substitution
- Stripe is invite-only in India (confirmed via Stripe's own support docs — self-signup not available)
- Asked in the community; a Pakistan-based intern hit the identical restriction and FlyRank
  confirmed publicly that using an alternative payment provider is acceptable, Stripe is not
  mandatory
- Proceeding with Razorpay as the substitute: same shape as Stripe's requirements —
  test mode (no card needed), signed webhooks (X-Razorpay-Signature, HMAC-SHA256),
  checkout flow, subscription events
- Everything else in the brief (idempotency, quota logic, cost math, architecture) is unchanged
## Phase 3 — Razorpay integration
- Built /checkout, /checkout-page, /webhooks/razorpay with Claude
- Ran a full real test-mode payment via net banking through ngrok tunnel
- Webhook signature verified, event processed, tenant 2 confirmed flipped free -> pro in DB
- Verified with direct SQL query, not just API response
## Phase 3 — Webhook security probes
- Forged signature test: request with fake X-Razorpay-Signature -> rejected (400)
- Replay test: same event_id sent twice with valid signature -> first "processed",
  second "duplicate_ignored" (test_webhook_replay.py, verified via script output)
  ## Phase 4 — Cost calculation
- Built app/pricing.py with Claude: separate per-category pricing, reasoning billed as output
- 7 pinned pytest tests, all passing
- Verified live: sent real /generate requests matching the pinned test's exact quantities,
  GET /usage/2 returned cost_cents=230, matching test_full_mixed_usage_total exactly