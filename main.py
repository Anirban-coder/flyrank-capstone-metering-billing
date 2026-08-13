import hmac
import hashlib
import os
import razorpay
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models
from app.pricing import total_ai_token_cost_cents, api_call_cost_cents
app = FastAPI()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

PRO_PLAN_PRICE_PAISE = 49900  # ₹499.00


class GenerateRequest(BaseModel):
    tenant_id: int
    usage_type: str  # "api_call" or "ai_tokens"
    quantity: int
    idempotency_key: str
    token_category: str | None = None


def get_current_usage(db: Session, tenant_id: int, usage_type: str) -> int:
    """Sum all usage_events of this type for this tenant. No date filtering yet —
    every seeded tenant is 'new' for this capstone's scope, so lifetime total
    doubles as 'this month' for now."""
    total = (
        db.query(func.coalesce(func.sum(models.UsageEvent.quantity), 0))
        .filter(
            models.UsageEvent.tenant_id == tenant_id,
            models.UsageEvent.type == usage_type,
        )
        .scalar()
    )
    return total


def get_quota(db: Session, tenant_id: int, usage_type: str) -> int:
    """Look up the tenant's active subscription, then that plan's limit for this usage type."""
    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.tenant_id == tenant_id, models.Subscription.status == "active")
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail=f"No active subscription for tenant {tenant_id}")

    plan = db.query(models.Plan).filter(models.Plan.id == sub.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if usage_type == "api_call":
        return plan.monthly_api_call_limit
    elif usage_type == "ai_tokens":
        return plan.monthly_token_limit
    else:
        raise HTTPException(status_code=400, detail=f"Unknown usage_type '{usage_type}'")


@app.post("/generate")
async def generate(body: GenerateRequest, db: Session = Depends(get_db)):
    # 1. Idempotency check FIRST, before touching quota logic at all.
    existing = (
        db.query(models.UsageEvent)
        .filter(models.UsageEvent.idempotency_key == body.idempotency_key)
        .first()
    )
    if existing:
        # Same key seen before — return the original result, do NOT record a new event.
        return {
            "status": "duplicate_ignored",
            "usage_event_id": existing.id,
            "tenant_id": existing.tenant_id,
            "type": existing.type,
            "quantity": existing.quantity,
        }

    # 2. Quota check — would this request push the tenant over their limit?
    current_usage = get_current_usage(db, body.tenant_id, body.usage_type)
    quota = get_quota(db, body.tenant_id, body.usage_type)

    if current_usage + body.quantity > quota:
        raise HTTPException(
            status_code=429,
            detail=f"Quota exceeded: {current_usage}/{quota} used, this request needs {body.quantity} more",
        )

    # 3. Record the usage event.
    event = models.UsageEvent(
        tenant_id=body.tenant_id,
        type=body.usage_type,
        quantity=body.quantity,
        idempotency_key=body.idempotency_key,
        token_category=body.token_category,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "status": "recorded",
        "usage_event_id": event.id,
        "tenant_id": event.tenant_id,
        "type": event.type,
        "quantity": event.quantity,
        "usage_after": current_usage + body.quantity,
        "quota": quota,
    }

class CheckoutRequest(BaseModel):
    tenant_id: int


@app.post("/checkout")
async def checkout(body: CheckoutRequest, db: Session = Depends(get_db)):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == body.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant {body.tenant_id} not found")

    order = razorpay_client.order.create({
        "amount": PRO_PLAN_PRICE_PAISE,
        "currency": "INR",
        "notes": {"tenant_id": str(body.tenant_id)},
    })

    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "checkout_page": f"/checkout-page?order_id={order['id']}&amount={order['amount']}",
    }


@app.get("/checkout-page", response_class=HTMLResponse)
async def checkout_page(order_id: str, amount: int):
    return f"""
    <html>
    <body>
      <h2>Upgrade to Pro</h2>
      <button id="pay-btn">Pay with Razorpay (test mode)</button>
      <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
      <script>
        document.getElementById('pay-btn').onclick = function() {{
          var options = {{
            "key": "{RAZORPAY_KEY_ID}",
            "amount": "{amount}",
            "currency": "INR",
            "name": "Billing Capstone",
            "order_id": "{order_id}",
            "handler": function (response) {{
              document.body.innerHTML = "<h3>Payment complete. Webhook will update your plan shortly.</h3>";
            }}
          }};
          var rzp = new Razorpay(options);
          rzp.open();
        }};
      </script>
    </body>
    </html>
    """


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    expected_signature = hmac.new(
        key=RAZORPAY_WEBHOOK_SECRET.encode(),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event_id = request.headers.get("X-Razorpay-Event-Id", payload.get("id", ""))

    already_processed = (
        db.query(models.ProcessedWebhookEvent)
        .filter(models.ProcessedWebhookEvent.stripe_event_id == event_id)
        .first()
    )
    if already_processed:
        return {"status": "duplicate_ignored"}

    event_type = payload.get("event")
    if event_type == "payment.captured":
        order_notes = payload["payload"]["payment"]["entity"].get("notes", {})
        tenant_id = int(order_notes.get("tenant_id"))

        pro_plan = db.query(models.Plan).filter(models.Plan.name == "pro").first()
        sub = (
            db.query(models.Subscription)
            .filter(models.Subscription.tenant_id == tenant_id, models.Subscription.status == "active")
            .first()
        )
        if sub and pro_plan:
            sub.plan_id = pro_plan.id
            db.commit()

    db.add(models.ProcessedWebhookEvent(stripe_event_id=event_id))
    db.commit()

    return {"status": "processed"}
@app.get("/usage/{tenant_id}")
async def get_usage(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.tenant_id == tenant_id, models.Subscription.status == "active")
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail=f"No active subscription for tenant {tenant_id}")

    plan = db.query(models.Plan).filter(models.Plan.id == sub.plan_id).first()

    # API calls: simple sum + flat-rate cost
    api_call_events = db.query(models.UsageEvent).filter(
        models.UsageEvent.tenant_id == tenant_id,
        models.UsageEvent.type == "api_call",
    ).all()
    api_call_total = sum(e.quantity for e in api_call_events)
    api_call_cost = api_call_cost_cents(api_call_total)

    # AI tokens: grouped by category, since each category has its own price.
    token_events = db.query(models.UsageEvent).filter(
        models.UsageEvent.tenant_id == tenant_id,
        models.UsageEvent.type == "ai_tokens",
    ).all()

    usage_by_category = {}
    for e in token_events:
        category = e.token_category or "input"  # fallback for any legacy rows with no category
        usage_by_category[category] = usage_by_category.get(category, 0) + e.quantity

    token_total = sum(usage_by_category.values())
    token_cost = total_ai_token_cost_cents(usage_by_category)

    return {
        "tenant_id": tenant_id,
        "plan": plan.name,
        "api_calls": {
            "used": api_call_total,
            "limit": plan.monthly_api_call_limit,
            "cost_cents": api_call_cost,
        },
        "ai_tokens": {
            "used": token_total,
            "limit": plan.monthly_token_limit,
            "by_category": usage_by_category,
            "cost_cents": token_cost,
        },
        "total_cost_cents": api_call_cost + token_cost,
    }