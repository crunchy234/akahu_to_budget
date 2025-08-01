"""Module for sending Pushcut notifications for new transactions."""

import os
import logging
import requests
from typing import List, Dict, Optional
from decimal import Decimal

# Pushcut configuration
PUSHCUT_API_KEY = os.getenv("PUSHCUT_API_KEY")
PUSHCUT_NOTIFICATION_NAME = os.getenv("PUSHCUT_NOTIFICATION_NAME", "New Transaction")
PUSHCUT_ENABLED = os.getenv("PUSHCUT_ENABLED", "false").lower() == "true"

# Optional: different notification for large transactions
PUSHCUT_LARGE_TRANSACTION_THRESHOLD = float(os.getenv("PUSHCUT_LARGE_TRANSACTION_THRESHOLD", "100"))
PUSHCUT_LARGE_NOTIFICATION_NAME = os.getenv("PUSHCUT_LARGE_NOTIFICATION_NAME", "Large Transaction Alert")


class PushcutNotifier:
    """Handles sending notifications via Pushcut API."""
    
    def __init__(self):
        self.api_key = PUSHCUT_API_KEY
        self.enabled = PUSHCUT_ENABLED
        self.base_url = "https://api.pushcut.io/v1"
        
        if self.enabled and not self.api_key:
            logging.warning("Pushcut notifications enabled but API key not provided")
            self.enabled = False
    
    def send_transaction_notification(self, transaction: Dict, account_name: str) -> bool:
        """Send a notification for a single transaction.
        
        Args:
            transaction: Dictionary containing transaction details
            account_name: Name of the account where transaction was synced
            
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            amount = abs(float(transaction.get('amount', 0)))
            payee = transaction.get('description', 'Unknown')
            date = transaction.get('date', 'Unknown date')
            
            # Determine notification type based on amount
            if amount >= PUSHCUT_LARGE_TRANSACTION_THRESHOLD:
                notification_name = PUSHCUT_LARGE_NOTIFICATION_NAME
                title = f"Large Transaction Alert: ${amount:.2f}"
            else:
                notification_name = PUSHCUT_NOTIFICATION_NAME
                title = f"New Transaction: ${amount:.2f}"
            
            # Format the notification
            text = f"{payee}\n{account_name}\n{date}"
            
            # Pushcut API payload
            payload = {
                "title": title,
                "text": text,
                "sound": "default"
            }
            
            # Send notification
            headers = {
                "API-Key": self.api_key,
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}/notifications/{notification_name}"
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                logging.debug(f"Pushcut notification sent for transaction: {payee} ${amount:.2f}")
                return True
            else:
                logging.warning(f"Failed to send Pushcut notification: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error sending Pushcut notification: {str(e)}")
            return False
    
    def send_batch_notification(self, transactions: List[Dict], account_name: str, batch_mode: bool = False) -> bool:
        """Send notifications for multiple transactions.
        
        Args:
            transactions: List of transaction dictionaries
            account_name: Name of the account where transactions were synced
            batch_mode: If True, send one summary notification. If False (default), send individual notifications
            
        Returns:
            bool: True if all notifications sent successfully, False otherwise
        """
        if not self.enabled or not transactions:
            return False
            
        # If batch_mode is False, send individual notifications
        if not batch_mode:
            success_count = 0
            for transaction in transactions:
                if self.send_transaction_notification(transaction, account_name):
                    success_count += 1
            
            if success_count == 0:
                return False
            elif success_count < len(transactions):
                logging.warning(f"Only {success_count}/{len(transactions)} notifications sent successfully")
            
            return success_count > 0
            
        try:
            total_amount = sum(abs(float(txn.get('amount', 0))) for txn in transactions)
            count = len(transactions)
            
            # Create summary
            title = f"{count} New Transactions: ${total_amount:.2f}"
            
            # Get details of first few transactions
            details = []
            for txn in transactions[:3]:  # Show first 3 transactions
                amount = abs(float(txn.get('amount', 0)))
                payee = txn.get('description', 'Unknown')
                details.append(f"${amount:.2f} - {payee}")
            
            if count > 3:
                details.append(f"... and {count - 3} more")
            
            text = f"{account_name}\n" + "\n".join(details)
            
            # Pushcut API payload
            payload = {
                "title": title,
                "text": text,
                "sound": "default"
            }
            
            # Send notification
            headers = {
                "API-Key": self.api_key,
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}/notifications/{PUSHCUT_NOTIFICATION_NAME}"
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                logging.debug(f"Pushcut batch notification sent for {count} transactions")
                return True
            else:
                logging.warning(f"Failed to send Pushcut batch notification: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error sending Pushcut batch notification: {str(e)}")
            return False


# Global notifier instance
pushcut_notifier = PushcutNotifier()