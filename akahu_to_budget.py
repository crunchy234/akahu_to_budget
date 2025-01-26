"""
Script for syncing transactions from Akahu to YNAB and Actual Budget.
Also provides webhook endpoints for real-time transaction syncing.
"""

from contextlib import contextmanager
import os
import logging
import signal
import sys
from actual import Actual
import requests

# Import from our modules package
from modules.sync_handler import sync_to_ab, sync_to_ynab
from modules.webhook_handler import create_flask_app
from modules.account_mapper import load_existing_mapping
from modules.config import AKAHU_ENDPOINT, AKAHU_HEADERS
from modules.config import RUN_SYNC_TO_AB, RUN_SYNC_TO_YNAB
from modules.config import ENVs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)


@contextmanager
def get_actual_client():
    """Context manager that yields an Actual client if RUN_SYNC_TO_AB is True,
    or None otherwise.
    This is needed because actualpy only works with contextmanager
    """
    if RUN_SYNC_TO_AB:
        try:
            logging.info(f"Attempting to connect to Actual server at {ENVs['ACTUAL_SERVER_URL']}")
            
            # Test the connection first
            
            with Actual(
                base_url=ENVs['ACTUAL_SERVER_URL'],
                password=ENVs['ACTUAL_PASSWORD'],
                file=ENVs['ACTUAL_SYNC_ID'],
                encryption_password=ENVs['ACTUAL_ENCRYPTION_KEY']
            ) as client:
                logging.info(f"Connected to AB: {client}")
                yield client
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to connect to Actual server: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"Response status: {e.response.status_code}")
                logging.error(f"Response headers: {dict(e.response.headers)}")
                logging.error(f"Response content: {e.response.text[:500]}")
            raise RuntimeError(f"Failed to connect to Actual server: {str(e)}") from None
    else:
        yield None

def signal_handler(sig, frame):
    logging.info("Received signal to terminate. Shutting down gracefully...")
    # Perform any cleanup here
    sys.exit(0)

def main():
    """Main entry point for the sync script."""

    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle kill

    # Load the existing mapping
    _, _, _, mapping_list = load_existing_mapping()
    with get_actual_client() as actual:
        # Initialize Actual if syncing to AB
        # Create Flask app with Actual client
        app = create_flask_app(actual, mapping_list, {
            'AKAHU_PUBLIC_KEY': os.getenv('AKAHU_PUBLIC_KEY', ''),  # RFU (Reserved For Future Use)
            'akahu_endpoint': AKAHU_ENDPOINT,
            'akahu_headers': AKAHU_HEADERS
        })

        development_mode = os.getenv('FLASK_ENV') == 'development'
        app.run(host="0.0.0.0", port=5000, debug=development_mode)

if __name__ == "__main__":
    main()
