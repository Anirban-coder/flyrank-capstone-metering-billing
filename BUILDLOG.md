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