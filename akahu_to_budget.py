"""
Script responsible for syncing transactions from Akahu to YNAB and Actual Budget.
Also provides webhook endpoints for real-time transaction syncing.
"""

import os
import logging
import pathlib
from threading import Thread
from dotenv import load_dotenv
from actual import Actual

# Import from our modules package
from modules.account_fetcher import get_akahu_balance
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

required_envs = [
    'ACTUAL_SERVER_URL',
    'ACTUAL_PASSWORD',
    'ACTUAL_ENCRYPTION_KEY',
    'ACTUAL_SYNC_ID',
    'AKAHU_USER_TOKEN',
    'AKAHU_APP_TOKEN',
    'AKAHU_PUBLIC_KEY',
    "YNAB_BEARER_TOKEN",
]

# Load environment variables into a dictionary for validation
ENVs = {key: os.getenv(key) for key in required_envs}
SYNC_TO_YNAB = True
SYNC_TO_AB = True

# Validate environment variables
for key, value in ENVs.items():
    if value is None:
        logging.error(f"Environment variable {key} is missing.")
        raise EnvironmentError(f"Missing required environment variable: {key}")

# API endpoints and headers
ynab_endpoint = "https://api.ynab.com/v1/"
ynab_headers = {"Authorization": f"Bearer {ENVs['YNAB_BEARER_TOKEN']}"}

akahu_endpoint = "https://api.akahu.io/v1/"
akahu_headers = {
    "Authorization": f"Bearer {ENVs['AKAHU_USER_TOKEN']}",
    "X-Akahu-ID": ENVs['AKAHU_APP_TOKEN']
}

def sync_to_ab(actual, mapping_list, akahu_accounts, actual_accounts, ynab_accounts):
    """Sync transactions from Akahu to Actual Budget."""
    for akahu_account_id, mapping_entry in mapping_list.items():
        actual_account_id = mapping_entry.get('actual_account_id')
        account_type = mapping_entry.get('account_type', 'On Budget')
        logging.info(f"Processing Akahu account: {akahu_account_id} linked to Actual account: {actual_account_id}")

        # Update balance for mapping entry
        mapping_entry['akahu_balance'] = get_akahu_balance(
            akahu_account_id, 
            akahu_endpoint, 
            akahu_headers
        )

        if account_type == 'Tracking':
            handle_tracking_account_actual(mapping_entry, actual)
        elif account_type == 'On Budget':
            if mapping_entry.get('actual_do_not_map'):
                logging.warning(
                    f"Skipping sync to Actual Budget for Akahu account {akahu_account_id}: account is configured to not be mapped."
                )
                continue

            if not (mapping_entry.get('actual_budget_id') and mapping_entry.get('actual_account_id')):
                logging.warning(
                    f"Skipping sync to Actual Budget for Akahu account {akahu_account_id}: Missing Actual Budget IDs."
                )
                continue

            last_reconciled_at = mapping_entry.get('actual_synced_datetime', '2024-01-01T00:00:00Z')
            akahu_df = get_all_akahu(
                akahu_account_id,
                akahu_endpoint,
                akahu_headers,
                last_reconciled_at
            )

            if akahu_df is not None and not akahu_df.empty:
                load_transactions_into_actual(akahu_df, mapping_entry, actual)
        else:
            logging.error(f"Unknown account type for Akahu account: {akahu_account_id}")

    save_mapping()

def sync_to_ynab(mapping_list):
    """Sync transactions from Akahu to YNAB."""
    for akahu_account_id, mapping_entry in mapping_list.items():
        ynab_account_id = mapping_entry.get('ynab_account_id')
        account_type = mapping_entry.get('account_type', 'On Budget')
        logging.info(f"Processing Akahu account: {akahu_account_id} linked to YNAB account: {ynab_account_id}")

        if account_type == 'On Budget':
            if mapping_entry.get('ynab_do_not_map'):
                logging.warning(
                    f"Skipping sync to YNAB for Akahu account {akahu_account_id}: account is configured to not be mapped."
                )
                continue

            if not (mapping_entry.get('ynab_budget_id') and mapping_entry.get('ynab_account_id')):
                logging.warning(
                    f"Skipping sync to YNAB for Akahu account {akahu_account_id}: Missing YNAB IDs."
                )
                continue

            last_reconciled_at = mapping_entry.get('ynab_synced_datetime', '2024-01-01T00:00:00Z')
            akahu_df = get_all_akahu(
                akahu_account_id,
                akahu_endpoint,
                akahu_headers,
                last_reconciled_at
            )

            if akahu_df is not None and not akahu_df.empty:
                # Clean and prepare transactions for YNAB
                cleaned_txn = clean_txn_for_ynab(akahu_df, ynab_account_id)
                
                # Load transactions into YNAB
                load_transactions_into_ynab(
                    cleaned_txn,
                    mapping_entry['ynab_budget_id'],
                    mapping_entry['ynab_account_id'],
                    ynab_endpoint,
                    ynab_headers
                )
        else:
            logging.error(f"Unknown account type for Akahu account: {akahu_account_id}")

    save_mapping({
        'akahu_accounts': akahu_accounts,
        'actual_accounts': actual_accounts,
        'ynab_accounts': ynab_accounts,
        'mapping': mapping_list
    })

def main():
    """Main entry point for the sync script."""
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
                    'akahu_endpoint': akahu_endpoint,
                    'akahu_headers': akahu_headers
                })

                # Start webhook server
                development_mode = os.getenv('FLASK_ENV') == 'development'
                start_webhook_server(app, development_mode)

                # Perform initial sync
                sync_to_ab(actual, mapping_list, akahu_accounts, actual_accounts, ynab_accounts)
        
        # Sync to YNAB if enabled
        if SYNC_TO_YNAB:
            sync_to_ynab(mapping_list, akahu_accounts, actual_accounts, ynab_accounts)

    except Exception as e:
        logging.exception("An unexpected error occurred during script execution.")

if __name__ == "__main__":
    main()