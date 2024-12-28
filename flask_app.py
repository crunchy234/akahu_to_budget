"""
Script for syncing transactions from Akahu to YNAB and Actual Budget.
Also provides webhook endpoints for real-time transaction syncing.
"""

from contextlib import contextmanager
import os
import logging
import argparse
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
        except Exception as e:
            logging.error(f"Failed to connect to Actual server: {str(e)}")
            raise
    else:
        yield None


# Create and export the Flask app for WSGI
def create_application():
    _, _, _, mapping_list = load_existing_mapping()
    with get_actual_client() as actual:
        app = create_flask_app(actual, mapping_list, {
            'AKAHU_PUBLIC_KEY': ENVs['AKAHU_PUBLIC_KEY'],
            'akahu_endpoint': AKAHU_ENDPOINT,
            'akahu_headers': AKAHU_HEADERS
        })
        return app


# Directly expose `application` for WSGI
application = create_application()


def run_sync():
    """Run sync operations directly."""
    logging.info("Starting direct sync...")
    actual_count = ynab_count = 0

    _, _, _, mapping_list = load_existing_mapping()

    if RUN_SYNC_TO_AB:
        with get_actual_client() as actual_client:
            actual_client.download_budget()
            actual_count = sync_to_ab(actual_client, mapping_list)
            logging.info(f"Synced {actual_count} accounts to Actual Budget.")

    if RUN_SYNC_TO_YNAB:
        ynab_count = sync_to_ynab(mapping_list)
        logging.info(f"Synced {ynab_count} accounts to YNAB.")

    logging.info(f"Sync completed. Actual count: {actual_count}, YNAB count: {ynab_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Flask app or perform direct sync.")
    parser.add_argument("--sync", action="store_true", help="Perform direct sync and exit.")
    args = parser.parse_args()

    if args.sync:
        run_sync()
    else:
        development_mode = os.getenv('FLASK_ENV') == 'development'
        application.run(host="127.0.0.1", port=5000, debug=development_mode)
