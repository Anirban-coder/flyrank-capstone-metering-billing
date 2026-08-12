from app.database import SessionLocal
from app import models

db = SessionLocal()

free_plan = models.Plan(name="free", monthly_api_call_limit=1000, monthly_token_limit=100000)
pro_plan = models.Plan(name="pro", monthly_api_call_limit=10000, monthly_token_limit=1000000)

db.add(free_plan)
db.add(pro_plan)
db.commit()

test_tenant = models.Tenant(name="Test Tenant")
db.add(test_tenant)
db.commit()

test_sub = models.Subscription(tenant_id=test_tenant.id, plan_id=free_plan.id, status="active")
db.add(test_sub)
db.commit()

print(f"Seeded: tenant_id={test_tenant.id}, free_plan_id={free_plan.id}, pro_plan_id={pro_plan.id}")

db.close()