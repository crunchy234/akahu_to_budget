#!/usr/bin/env python3
"""
Script to fetch pending transactions from Akahu and send notifications via Pushcut.

This script:
1. Fetches all pending transactions from Akahu accounts
2. Tracks which transactions have already been notified
3. Sends Pushcut notifications for new pending transactions

Note: Pending transactions don't have unique IDs, so we use a hash of transaction
properties to track notifications.
"""

import os
import json
import logging
import requests
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Set
from pathlib import Path

from modules.config import AKAHU_ENDPOINT, AKAHU_HEADERS
from modules.pushcut_notifier import pushcut_notifier
from modules.account_mapper import load_existing_mapping
from modules.transaction_handler import refresh_akahu_account_transactions

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pending_transactions.log'),
        logging.StreamHandler()
    ]
)

# File to track sent notifications
SENT_NOTIFICATIONS_FILE = "sent_pending_notifications.json"


def generate_transaction_hash(txn: Dict) -> str:
    """Generate a hash-based ID for a pending transaction.
    
    Since pending transactions don't have unique IDs, we create a hash
    based on the transaction properties that are unlikely to change.
    """
    # Use account, date, amount, and description to create a unique hash
    # We use _account_id which we added when fetching transactions
    account_id = txn.get("_account_id", txn.get("_account", ""))
    date = txn.get("date", "")
    amount = str(txn.get("amount", 0))
    description = txn.get("description", "")
    
    # Create a string combining these fields
    hash_string = f"{account_id}|{date}|{amount}|{description}"
    
    # Generate a hash
    return hashlib.sha256(hash_string.encode()).hexdigest()[:16]


def load_sent_notifications() -> Set[str]:
    """Load the set of transaction IDs that have already been notified."""
    if not Path(SENT_NOTIFICATIONS_FILE).exists():
        return set()

    try:
        with open(SENT_NOTIFICATIONS_FILE, 'r') as f:
            data = json.load(f)
            # Clean up old entries (older than 30 days)
            cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
            cleaned_data = {
                txn_id: timestamp
                for txn_id, timestamp in data.items()
                if timestamp > cutoff_date
            }
            # Save cleaned data if different
            if len(cleaned_data) != len(data):
                save_sent_notifications(cleaned_data)
            return set(cleaned_data.keys())
    except Exception as e:
        logging.error(f"Error loading sent notifications: {e}")
        return set()


def save_sent_notifications(notifications: Dict[str, str]):
    """Save the set of notified transaction IDs with timestamps."""
    try:
        with open(SENT_NOTIFICATIONS_FILE, 'w') as f:
            json.dump(notifications, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving sent notifications: {e}")


def fetch_pending_transactions(akahu_account_id: str) -> List[Dict]:
    """Fetch pending transactions for a specific Akahu account."""
    try:
        url = f"{AKAHU_ENDPOINT}/accounts/{akahu_account_id}/transactions/pending"

        response = requests.get(url, headers=AKAHU_HEADERS)
        response.raise_for_status()

        data = response.json()
        return data.get("items", [])

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch pending transactions for account {akahu_account_id}: {e}")
        return []


def get_all_pending_transactions() -> List[Dict]:
    """Fetch all pending transactions from all mapped Akahu accounts."""
    # Load account mappings
    akahu_accounts, _, _, mappings = load_existing_mapping()

    all_pending = []

    for akahu_account_id, mapping_entry in mappings.items():
        # Skip if account is set to not sync
        if mapping_entry.get("ynab_do_not_map") and mapping_entry.get("actual_do_not_map"):
            logging.debug(f"Skipping account {akahu_account_id}: configured not to sync")
            continue

        account_name = mapping_entry.get("akahu_name", "Unknown Account")
        logging.info(f"Fetching pending transactions for {account_name} ({akahu_account_id})")

        pending_txns = fetch_pending_transactions(akahu_account_id)

        # Add account information to each transaction
        for txn in pending_txns:
            txn["_account_id"] = akahu_account_id
            txn["_account_name"] = account_name

        all_pending.extend(pending_txns)

    return all_pending


def main():
    """Main function to check pending transactions and send notifications."""
    logging.info("Starting pending transactions check...")

    # Check if Pushcut is enabled
    if not pushcut_notifier.enabled:
        logging.warning("Pushcut notifications are not enabled. Set PUSHCUT_ENABLED=true to enable.")
        return

    # Load previously sent notifications
    sent_notifications = load_sent_notifications()
    notifications_data = {}

    # Load existing data for updating
    if Path(SENT_NOTIFICATIONS_FILE).exists():
        with open(SENT_NOTIFICATIONS_FILE, 'r') as f:
            notifications_data = json.load(f)

    # Refresh all accounts
    refresh_akahu_account_transactions()
    # Get all pending transactions
    pending_transactions = get_all_pending_transactions()

    if not pending_transactions:
        logging.info("No pending transactions found.")
        return

    logging.info(f"Found {len(pending_transactions)} pending transactions")

    # Filter out already notified transactions
    new_transactions = []
    for txn in pending_transactions:
        # Generate a hash-based ID for the pending transaction
        txn_hash = generate_transaction_hash(txn)
        txn["_generated_id"] = txn_hash  # Store for later use
        
        if txn_hash not in sent_notifications:
            new_transactions.append(txn)

    if not new_transactions:
        logging.info("No new pending transactions to notify.")
        return

    logging.info(f"Found {len(new_transactions)} new pending transactions to notify")

    # Send notifications for new transactions
    success_count = 0
    for txn in new_transactions:
        account_name = txn.get("_account_name", "Unknown Account")

        # Send notification
        if pushcut_notifier.send_transaction_notification(txn, account_name):
            # Mark as sent using the generated hash ID
            txn_hash = txn.get("_generated_id")
            notifications_data[txn_hash] = datetime.now().isoformat()
            success_count += 1

            # Log transaction details
            amount = abs(float(txn.get('amount', 0)))
            payee = txn.get('description', 'Unknown')
            logging.info(f"Notified: {payee} - ${amount:.2f} ({account_name})")

    # Save updated notifications data
    if success_count > 0:
        save_sent_notifications(notifications_data)
        logging.info(f"Successfully sent {success_count} notifications")
    else:
        logging.warning("Failed to send any notifications")

    logging.info("Pending transactions check complete.")


if __name__ == "__main__":
    main()
