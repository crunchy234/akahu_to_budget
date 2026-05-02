import os
import urllib.request
import json
import logging

# Setup basic logging to systemd journal
logger = logging.getLogger(__name__)

SURE_API_TOKEN = os.environ.get("SURE_API_TOKEN")
SURE_URL = "http://127.0.0.1:8084/api/v1/transactions" 

def push_to_sure(transaction, sure_account_id):
    if not SURE_API_TOKEN:
        logger.warning("Missing SURE_API_TOKEN in environment. Skipping Sure Finance sync.")
        return

    # Extract clean data from the Akahu transaction object
    amount = transaction.get("amount")
    date_string = transaction.get("date", "")[:10] # Enforce YYYY-MM-DD
    name = transaction.get("merchant_name") or transaction.get("description") or "Unknown Transaction"

    # Wrap the payload inside a 'transaction' root key for Rails Strong Parameters
    payload = {
        "transaction": {
            "account_id": sure_account_id,
            "date": date_string,
            "amount": amount,
            "name": name,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(SURE_URL, data=data, headers={
        "X-Api-Key": SURE_API_TOKEN,
        "Content-Type": "application/json"
    })

    try:
        urllib.request.urlopen(req)
        logger.info(f"Sure Sync Success: {name} for ${amount}")
    except Exception as e:
        logger.error(f"Sure Sync Failed: {e}")
        # CRITICAL: We must raise the exception so flask_app.py knows it failed
        # and doesn't increment the success counter!
        raise e