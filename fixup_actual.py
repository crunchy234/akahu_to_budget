import os
from dotenv import load_dotenv
import logging
from actual import Actual
from actual.queries import get_transactions
import traceback

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Read environment variables
ENVs = {
    "ACTUAL_SERVER_URL": os.getenv("ACTUAL_SERVER_URL"),
    "ACTUAL_PASSWORD": os.getenv("ACTUAL_PASSWORD"),
    "ACTUAL_SYNC_ID": os.getenv("ACTUAL_SYNC_ID"),
    "ACTUAL_ENCRYPTION_KEY": os.getenv("ACTUAL_ENCRYPTION_KEY"),
}

# Ensure all necessary settings are present
missing_keys = [key for key, value in ENVs.items() if not value]
if missing_keys:
    logging.error(f"Missing required environment variables: {', '.join(missing_keys)}")
    exit(1)

logging.info("About to attempt Actual connection with:")
logging.info(f"Base URL: {ENVs['ACTUAL_SERVER_URL']}")
logging.info(f"Sync ID: {ENVs['ACTUAL_SYNC_ID']}")
# Don't log passwords!

try:
    # First try just making a connection
    with Actual(
        base_url=ENVs['ACTUAL_SERVER_URL'],
        password=ENVs['ACTUAL_PASSWORD'],
        file=ENVs['ACTUAL_SYNC_ID'],
        encryption_password=ENVs['ACTUAL_ENCRYPTION_KEY']
    ) as actual:
        logging.info("Successfully connected to Actual")
        
        # Try downloading the budget
        logging.info("Attempting to download budget...")
        actual.download_budget()
        logging.info("Successfully downloaded budget")

        # Fetch transactions and log details
        logging.info("Attempting to fetch transactions...")
        transactions = get_transactions(actual.session)
        logging.info(f"Successfully fetched {len(transactions)} transactions")
        
        # Log a few transactions for verification
        for t in transactions[:5]:  # Just show first 5 for testing
            account_name = t.account.name if t.account else "Unknown Account"
            category = t.category.name if t.category else "Unknown Category"
            logging.info(f"{t.date} - {account_name} - {t.notes} - {t.amount} - {category}")

except Exception as e:
    logging.error(f"Failed to connect to Actual server or process transactions: {str(e)}")
    logging.error(f"Error type: {type(e)}")
    logging.error(f"Full traceback: {traceback.format_exc()}")
    
    # Additional error information if it's a request error
    if hasattr(e, 'response') and e.response is not None:
        logging.debug(f"Response status: {e.response.status_code}")
        logging.debug(f"Response headers: {dict(e.response.headers)}")
        logging.debug(f"Response content: {e.response.text[:500]}")
    raise