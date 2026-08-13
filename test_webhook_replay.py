import hmac
import hashlib
import json
import os
import urllib.request
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
URL = "http://localhost:8000/webhooks/razorpay"

payload = {
    "id": "evt_manual_replay_test_001",
    "event": "payment.captured",
    "payload": {
        "payment": {
            "entity": {
                "notes": {"tenant_id": "2"}
            }
        }
    },
}

body_bytes = json.dumps(payload).encode()

signature = hmac.new(
    key=WEBHOOK_SECRET.encode(),
    msg=body_bytes,
    digestmod=hashlib.sha256,
).hexdigest()


def send():
    req = urllib.request.Request(
        URL,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": payload["id"],
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.status, resp.read().decode())


print("First send (should be 'processed'):")
send()

print("Second send, same event id (should be 'duplicate_ignored'):")
send()