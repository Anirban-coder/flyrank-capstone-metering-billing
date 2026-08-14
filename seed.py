from app.database import SessionLocal
from app import models
 
db = SessionLocal()
 
free_plan = db.query(models.Plan).filter(models.Plan.name == "free").first()
 
demo_tenant = models.Tenant(name="Demo Tenant")
db.add(demo_tenant)
db.commit()
 
demo_sub = models.Subscription(tenant_id=demo_tenant.id, plan_id=free_plan.id, status="active")
db.add(demo_sub)
db.commit()
 
# Pre-load usage close to (but not at) the free plan's 1,000 call limit,
# so the demo doesn't need 995 individual curl calls to reach the boundary live.
for i in range(990):
    db.add(models.UsageEvent(
        tenant_id=demo_tenant.id,
        type="api_call",
        quantity=1,
        idempotency_key=f"demo-preload-{i}",
    ))
db.commit()
 
print(f"Demo tenant ready: tenant_id={demo_tenant.id}, currently at 990/1000 API calls")
 
db.close()
 