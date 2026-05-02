import os
import urllib.request
import json
import logging
from datetime import datetime, timedelta

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
    
    # Timezone Conversion Logic
    raw_date = transaction.get("date")
    if raw_date:
        try:
            # Strip off the 'Z' and any fractional seconds (e.g., .000)
            if '.' in raw_date:
                raw_date = raw_date[:raw_date.index('.')]
            if raw_date.endswith('Z'):
                raw_date = raw_date[:-1]
                
            # Parse the UTC time and add 12 hours for NZT
            utc_time = datetime.fromisoformat(raw_date)
            # Or +13 hours during Daylight Saving Time, depending on your needs. 
            # We'll stick to a standard +12 for this example.
            nzt_time = utc_time + timedelta(hours=12)
            date_string = nzt_time.strftime("%Y-%m-%d")
        except ValueError:
            # Fallback if the date format is completely unexpected
            logger.warning(f"Could not parse date string: {raw_date}. Falling back to raw slice.")
            date_string = raw_date[:10]
    else:
        date_string = ""

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
        raise e