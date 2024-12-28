"""
Script for syncing transactions from Akahu to YNAB and Actual Budget.
Also provides webhook endpoints for real-time transaction syncing.
"""

from contextlib import contextmanager
import logging
from actual import Actual
import requests

# Import from our modules package
from modules.webhook_handler import create_flask_app
from modules.account_mapper import load_existing_mapping
from modules.config import AKAHU_ENDPOINT, AKAHU_HEADERS
from modules.config import RUN_SYNC_TO_AB
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
            raise RuntimeError(f"Failed to connect to Actual server: {str(e)}") from None
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
