from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models

app = FastAPI()


class GenerateRequest(BaseModel):
    tenant_id: int
    usage_type: str  # "api_call" or "ai_tokens"
    quantity: int
    idempotency_key: str


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