"""Module for handling transaction processing and syncing."""
import datetime
import decimal
import logging
import pandas as pd
import requests
from actual.queries import create_transaction, reconcile_transaction

from .account_fetcher import get_akahu_balance, get_actual_balance

def get_all_akahu(akahu_account_id, akahu_endpoint, akahu_headers, last_reconciled_at=None):
    """Fetch all transactions from Akahu for a given account, supporting pagination."""
    query_params = {}
    res = None
    total_txn = 0

    if last_reconciled_at:
        query_params['start'] = last_reconciled_at
    else:
        start_of_time = "2024-01-01T00:00:00Z"
        query_params['start'] = start_of_time

    next_cursor = 'first time'
    while next_cursor is not None:
        if next_cursor != 'first time':
            query_params['cursor'] = next_cursor

        try:
            response = requests.get(
                f"{akahu_endpoint}/accounts/{akahu_account_id}/transactions",
                params=query_params,
                headers=akahu_headers
            )
            response.raise_for_status()
            akahu_txn_json = response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error occurred during Akahu API request: {str(e)}")
            break

        akahu_txn = pd.DataFrame(akahu_txn_json.get('items', []))
        if res is None:
            res = akahu_txn.copy()
        else:
            res = pd.concat([res, akahu_txn])

        num_txn = akahu_txn.shape[0]
        total_txn += num_txn
        logging.info(f"Fetched {num_txn} transactions from Akahu.")

        if num_txn == 0 or 'cursor' not in akahu_txn_json or 'next' not in akahu_txn_json['cursor']:
            next_cursor = None
        else:
            next_cursor = akahu_txn_json['cursor']['next']

    logging.info(f"Finished reading {total_txn} transactions from Akahu.")
    return res

def load_transactions_into_actual(transactions, mapping_entry, actual):
    """Load transactions into Actual Budget using the mapping information."""
    if transactions is None or transactions.empty:
        logging.info("No transactions to load into Actual.")
        return

    actual_account_id = mapping_entry['actual_account_id']
    imported_transactions = []

    for _, txn in transactions.iterrows():
        transaction_date = txn.get("date")
        payee_name = txn.get("description")
        notes = f"Akahu transaction: {txn.get('description')}"
        amount = decimal.Decimal(txn.get("amount") * -1)
        imported_id = txn.get("_id")
        cleared = True

        try:
            # Use the imported reconcile_transaction function with the session directly
            # Parse ISO format date and extract just the date component
            parsed_date = datetime.datetime.strptime(transaction_date, "%Y-%m-%dT%H:%M:%SZ").date()
            reconciled_transaction = reconcile_transaction(
                actual.session,
                date=parsed_date,
                account=actual_account_id,
                payee=payee_name,
                notes=notes,
                amount=amount,
                imported_id=imported_id,
                cleared=cleared,
                imported_payee=payee_name,
                already_matched=imported_transactions
            )

            if reconciled_transaction.changed():
                imported_transactions.append(reconciled_transaction)
            logging.info(f"Successfully reconciled transaction: {imported_id}")

        except Exception as e:
            logging.error(f"Failed to reconcile transaction {imported_id} into Actual: {str(e)}")
            raise

    mapping_entry['actual_synced_datetime'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def handle_tracking_account_actual(mapping_entry, actual):
    """Handle tracking accounts by checking and adjusting balances."""
    akahu_account_id = mapping_entry['akahu_id']
    actual_account_id = mapping_entry['actual_account_id']
    akahu_account_name = mapping_entry['akahu_name']

    try:
        logging.info(f"Handling tracking account: {akahu_account_name} (Akahu ID: {akahu_account_id})")
        akahu_balance = round(mapping_entry['akahu_balance'] * 100)
        actual_balance = get_actual_balance(actual, actual_account_id)

        if akahu_balance != actual_balance:
            adjustment_amount = decimal.Decimal(akahu_balance - actual_balance) / 100
            transaction_date = datetime.datetime.utcnow().date()
            payee_name = "Balance Adjustment"
            notes = f"Adjusted from {actual_balance / 100} to {akahu_balance / 100} to reconcile tracking account."

            # Use the imported create_transaction function with the session directly
            create_transaction(
                actual.session,
                date=transaction_date,
                account=actual_account_id,
                payee=payee_name,
                notes=notes,
                amount=adjustment_amount,
                imported_id=f"adjustment_{datetime.datetime.utcnow().isoformat()}",
                cleared=True,
                imported_payee=payee_name
            )
            logging.info(f"Created balance adjustment transaction for {akahu_account_name}")
        else:
            logging.info(f"No balance adjustment needed for {akahu_account_name}")

    except Exception as e:
        logging.error(f"Error handling tracking account {akahu_account_name}: {str(e)}")

def get_payee_name(row):
    """Extract the payee name from the given row, prioritizing the merchant name if available."""
    try:
        res = None
        if "merchant" in row and not pd.isna(row["merchant"]):
            if "name" in row["merchant"]:
                res = row['merchant']['name']
        if res is None:
            res = row['description']
    except (TypeError, ValueError) as e:
        logging.error(f"Error extracting payee name from row: {e}, row: {row}")
        res = "Unknown"
    return res

def convert_to_nzt(date_str):
    """Convert a given date string to New Zealand Time (NZT)."""
    try:
        if date_str is None:
            logging.warning("Input date string is None.")
            return None
        utc_time = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        nzt_time = utc_time + datetime.timedelta(hours=13)
        return nzt_time.strftime("%Y-%m-%d")
    except ValueError as e:
        logging.error(f"Error converting date string to NZT: {e}, date_str: {date_str}")
        return None

def clean_txn_for_ynab(akahu_txn, ynab_account_id):
    """Clean and transform Akahu transactions to prepare them for YNAB import."""
    akahu_txn['payee_name'] = akahu_txn.apply(get_payee_name, axis=1)
    akahu_txn['memo'] = akahu_txn['description']
    akahu_txn_useful = akahu_txn[['_id', 'date', 'amount', 'memo', 'payee_name']].rename(columns={'_id': 'id'}, errors='ignore')
    akahu_txn_useful['amount'] = akahu_txn_useful['amount'].apply(lambda x: str(int(x * 1000)))
    akahu_txn_useful['cleared'] = 'cleared'
    akahu_txn_useful['date'] = akahu_txn_useful.apply(lambda row: convert_to_nzt(row['date']), axis=1)
    akahu_txn_useful['import_id'] = akahu_txn_useful['id']
    akahu_txn_useful['flag_color'] = 'red'
    akahu_txn_useful['account_id'] = ynab_account_id

    return akahu_txn_useful

def load_transactions_into_ynab(akahu_txn, ynab_budget_id, ynab_account_id, ynab_endpoint, ynab_headers):
    """Save transactions from Akahu to YNAB."""
    uri = f"{ynab_endpoint}budgets/{ynab_budget_id}/transactions"
    transactions_list = akahu_txn.to_dict(orient='records')

    ynab_api_payload = {
        "transactions": transactions_list
    }
    try:
        response = requests.post(uri, headers=ynab_headers, json=ynab_api_payload)
        response.raise_for_status()

        ynab_response = response.json()
        if 'duplicate_import_ids' in ynab_response['data'] and len(ynab_response['data']['duplicate_import_ids']) > 0:
            dup_str = f"Skipped {len(ynab_response['data']['duplicate_import_ids'])} duplicates"
        else:
            dup_str = "No duplicates"

        if len(ynab_response['data']['transactions']) == 0:
            logging.info(f"No new transactions loaded to YNAB - {dup_str}")
        else:
            logging.info(f"Successfully loaded {len(ynab_response['data']['transactions'])} transactions to YNAB - {dup_str}")

        return ynab_response

    except requests.exceptions.RequestException as e:
        logging.error(f"Error making the API request to YNAB: {e}")
        if response is not None:
            logging.error(f"API response content: {response.text}")
        return None

def create_adjustment_txn_ynab(ynab_budget_id, ynab_account_id, akahu_balance, ynab_balance, ynab_endpoint, ynab_headers):
    """Create an adjustment transaction in YNAB to reconcile the balance."""
    try:
        balance_difference = akahu_balance - ynab_balance
        if balance_difference == 0:
            logging.info("No adjustment needed; balances are already in sync.")
            return
        
        uri = f"{ynab_endpoint}budgets/{ynab_budget_id}/transactions"
        transaction = {
            "transaction": {
                "account_id": ynab_account_id,
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "amount": balance_difference,
                "payee_name": "Balance Adjustment",
                "memo": f"Adjusted from ${ynab_balance/1000:.2f} to ${akahu_balance/1000:.2f} based on retrieved balance",
                "cleared": "cleared",
                "approved": True
            }
        }
        
        response = requests.post(uri, headers=ynab_headers, json=transaction)
        response.raise_for_status()
        logging.info(f"Created balance adjustment transaction for {balance_difference}")
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to create balance adjustment transaction: {e}")