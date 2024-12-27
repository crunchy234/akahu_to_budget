"""
Script responsible for syncing transactions from Akahu to YNAB and Actual Budget.
Also provides webhook endpoints for real-time transaction syncing.
"""

import os
import logging
import pathlib
import signal
import sys
from threading import Thread
from dotenv import load_dotenv
from actual import Actual

# Import from our modules package
from modules.account_fetcher import get_akahu_balance
from modules.sync_handler import sync_to_ab, sync_to_ynab
from modules.transaction_handler import (
    get_all_akahu,
    load_transactions_into_actual,
    load_transactions_into_ynab,
    handle_tracking_account_actual,
    clean_txn_for_ynab,
    create_adjustment_txn_ynab
)
from modules.webhook_handler import create_flask_app, start_webhook_server
from modules.account_mapper import load_existing_mapping, save_mapping
from modules.config import AKAHU_ENDPOINT, AKAHU_HEADERS, ENVs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)


# Load environment variables into a dictionary for validation
SYNC_TO_YNAB = True
SYNC_TO_AB = True



def signal_handler(sig, frame):
    logging.info("Received interrupt signal. Shutting down gracefully...")
    sys.exit(0)

def main():
    """Main entry point for the sync script."""

    # Register the signal handler for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Load the existing mapping
        akahu_accounts, actual_accounts, ynab_accounts, mapping_list = load_existing_mapping()

        # Initialize Actual if syncing to AB
        if SYNC_TO_AB:
            with Actual(
                base_url=ENVs['ACTUAL_SERVER_URL'],
                password=ENVs['ACTUAL_PASSWORD'],
                file=ENVs['ACTUAL_SYNC_ID'],
                encryption_password=ENVs['ACTUAL_ENCRYPTION_KEY']
            ) as actual:
                # Create Flask app with Actual client
                app = create_flask_app(actual, mapping_list, {
                    'AKAHU_PUBLIC_KEY': ENVs['AKAHU_PUBLIC_KEY'],
                    'akahu_endpoint': AKAHU_ENDPOINT,
                    'akahu_headers': AKAHU_HEADERS
                })

                # Start webhook server
                development_mode = os.getenv('FLASK_ENV') == 'development'
                start_webhook_server(app, development_mode)

                try:
                    # Perform initial sync
                    if SYNC_TO_AB:
                        sync_to_ab(actual, mapping_list, akahu_accounts, actual_accounts, ynab_accounts)
                    
                    # Sync to YNAB if enabled
                    if SYNC_TO_YNAB:
                        sync_to_ynab(mapping_list, akahu_accounts, actual_accounts, ynab_accounts)

                    # Keep the main thread alive to handle signals
                    while True:
                        signal.pause()
                except KeyboardInterrupt:
                    logging.info("Received interrupt signal. Shutting down gracefully...")
                    sys.exit(0)

    except Exception as e:
        logging.exception("An unexpected error occurred during script execution.")
        sys.exit(1)

if __name__ == "__main__":
    main()