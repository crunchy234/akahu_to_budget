import os
import urllib.request
import json
import logging
from datetime import datetime, timezone
import zoneinfo

# Setup basic logging to systemd journal
logger = logging.getLogger(__name__)

SURE_API_TOKEN = os.environ.get("SURE_API_TOKEN")
SURE_URL = "http://127.0.0.1:8084/api/v1/transactions" 

def push_to_sure(transaction, sure_account_id):
    if not SURE_API_TOKEN:
        logger.warning("Missing SURE_API_TOKEN in environment. Skipping Sure Finance sync.")
        return

    # FLIP THE SIGN: Akahu positive (expense) becomes Sure negative (expense)
    raw_amount = transaction.get("amount", 0)
    amount = -raw_amount 
    
    # Precise Timezone Conversion Logic
    raw_date = transaction.get("date")
    if raw_date:
        try:
            if '.' in raw_date:
                raw_date = raw_date[:raw_date.index('.')]
            if raw_date.endswith('Z'):
                raw_date = raw_date[:-1]
                
            # Parse as a UTC-aware datetime object
            utc_time = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
            
            # Convert natively to Pacific/Auckland (handles both NZST and NZDT automatically)
            nz_tz = zoneinfo.ZoneInfo("Pacific/Auckland")
            nzt_time = utc_time.astimezone(nz_tz)
            date_string = nzt_time.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Could not parse date string: {raw_date}. Error: {e}. Falling back.")
            date_string = raw_date[:10]
    else:
        date_string = ""

    name = transaction.get("merchant_name") or transaction.get("description") or "Unknown Transaction"
    akahu_id = transaction.get("_id", "")

    # Wrap the payload and include the external_id for robust deduplication
    payload = {
        "transaction": {
            "account_id": sure_account_id,
            "date": date_string,
            "amount": amount,
            "name": name,
            "external_id": akahu_id 
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