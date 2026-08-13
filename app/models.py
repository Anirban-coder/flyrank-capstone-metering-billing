from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    monthly_api_call_limit = Column(Integer, nullable=False)
    monthly_token_limit = Column(Integer, nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    type = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    token_category = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"

    stripe_event_id = Column(String, primary_key=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())