import logging
from modules.account_fetcher import get_akahu_balance
from modules.account_mapper import save_mapping
from modules.transaction_handler import clean_txn_for_ynab, get_all_akahu, handle_tracking_account_actual, load_transactions_into_actual, load_transactions_into_ynab
from modules.config import YNAB_ENDPOINT, YNAB_HEADERS, AKAHU_ENDPOINT, AKAHU_HEADERS


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
                AKAHU_ENDPOINT,
                AKAHU_HEADERS,
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
                    YNAB_ENDPOINT,
                    YNAB_HEADERS
                )
        else:
            logging.error(f"Unknown account type for Akahu account: {akahu_account_id}")

    save_mapping() # BROKEN CALL

def sync_to_ab(actual, mapping_list, akahu_accounts, actual_accounts, ynab_accounts):
    """Sync transactions from Akahu to Actual Budget."""
    for akahu_account_id, mapping_entry in mapping_list.items():
        actual_account_id = mapping_entry.get('actual_account_id')
        account_type = mapping_entry.get('account_type', 'On Budget')
        logging.info(f"Processing Akahu account: {akahu_account_id} linked to Actual account: {actual_account_id}")

        # Update balance for mapping entry
        mapping_entry['akahu_balance'] = get_akahu_balance(
            akahu_account_id, 
            AKAHU_ENDPOINT, 
            AKAHU_HEADERS
        )

        transactions_processed = False
        
        if account_type == 'Tracking':
            handle_tracking_account_actual(mapping_entry, actual)
            transactions_processed = True
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
                AKAHU_ENDPOINT,
                AKAHU_HEADERS,
                last_reconciled_at
            )

            if akahu_df is not None and not akahu_df.empty:
                logging.info("About to load transactions into Actual Budget...")
                load_transactions_into_actual(akahu_df, mapping_entry, actual)
                transactions_processed = True
        else:
            logging.error(f"Unknown account type for Akahu account: {akahu_account_id}")

        # Commit changes if any transactions were processed
        if transactions_processed:
            logging.info("Finished processing transactions, about to commit...")
            try:
                commit_result = actual.commit()
                logging.info(f"Commit result: {commit_result}")
                actual.download_budget()  # Force refresh after commit
            except Exception as e:
                logging.error(f"Error during commit: {str(e)}")
                logging.error(f"Error type: {type(e)}")
                raise

    save_mapping() # BROKEN CALL
