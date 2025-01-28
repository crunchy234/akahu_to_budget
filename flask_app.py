"""
Script for syncing transactions from Akahu to YNAB and Actual Budget.
Also provides webhook endpoints for real-time transaction syncing.
"""

from contextlib import contextmanager
import os
import logging
import argparse
import signal
import sys
import requests
from actual import Actual

# Import from our modules package
from modules.sync_handler import sync_to_ab, sync_to_ynab
from modules.account_mapper import load_existing_mapping
from modules.config import AKAHU_ENDPOINT, AKAHU_HEADERS
from modules.config import RUN_SYNC_TO_AB, RUN_SYNC_TO_YNAB
from modules.config import ENVs
from modules.webhook_handler import create_flask_app

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


# Create and export the Flask app for WSGI
def signal_handler(sig, frame):
    logging.info("Received signal to terminate. Shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Handle kill

def create_application():
    """Create Flask application."""
    _, _, _, mapping_list = load_existing_mapping()
    
    with get_actual_client() as actual_client:
        app = create_flask_app(actual_client, mapping_list, {
            'AKAHU_PUBLIC_KEY': os.getenv('AKAHU_PUBLIC_KEY', ''),  # RFU (Reserved For Future Use)
            'akahu_endpoint': AKAHU_ENDPOINT,
            'akahu_headers': AKAHU_HEADERS
        })
        return app


def run_sync():
    """Run sync operations directly."""
    logging.info("Starting direct sync...")
    actual_count = ynab_count = 0

    _, _, _, mapping_list = load_existing_mapping()

    with get_actual_client() as actual_client:
        if RUN_SYNC_TO_AB and actual_client:
            actual_client.download_budget()
            actual_count = sync_to_ab(actual_client, mapping_list)
            logging.info(f"Synced {actual_count} accounts to Actual Budget.")

        if RUN_SYNC_TO_YNAB:
            ynab_count = sync_to_ynab(mapping_list)
            logging.info(f"Synced {ynab_count} accounts to YNAB.")

    logging.info(f"Sync completed. Actual count: {actual_count}, YNAB count: {ynab_count}")


# Create and expose the Flask application for WSGI
application = create_application()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Flask app or perform direct sync.")
    parser.add_argument("--sync", action="store_true", help="Perform direct sync and exit.")
    args = parser.parse_args()

    if args.sync:
        run_sync()
    else:
        development_mode = os.getenv('FLASK_ENV') == 'development'
        application.run(host="0.0.0.0", port=5000, debug=development_mode)
