import os
from dotenv import load_dotenv
import logging
from actual import Actual
from actual.queries import get_transactions, get_accounts, create_transaction
import traceback
from datetime import datetime
import decimal
import json
from modules.account_fetcher import get_akahu_balance
from modules.config import AKAHU_ENDPOINT, AKAHU_HEADERS

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Read environment variables
ENVs = {
    "ACTUAL_SERVER_URL": os.getenv("ACTUAL_SERVER_URL"),
    "ACTUAL_PASSWORD": os.getenv("ACTUAL_PASSWORD"),
    "ACTUAL_SYNC_ID": os.getenv("ACTUAL_SYNC_ID"),
    "ACTUAL_ENCRYPTION_KEY": os.getenv("ACTUAL_ENCRYPTION_KEY"),
}

def load_mapping():
    """Load the account mapping file."""
    with open('akahu_budget_mapping.json', 'r') as f:
        return json.load(f)

def fix_account_balances(actual, mapping_data):
    """Fix balances for all tracking accounts."""
    accounts = get_accounts(actual.session)
    mapping = mapping_data.get('mapping', {})
    
    for account in accounts:
        if account.closed:
            continue
            
        # Find corresponding mapping entry
        mapping_entry = None
        for akahu_id, entry in mapping.items():
            if entry.get('actual_account_id') == account.id:
                mapping_entry = entry
                mapping_entry['akahu_id'] = akahu_id
                break
                
        if not mapping_entry or mapping_entry.get('account_type') != 'Tracking':
            continue
            
        logging.info(f"\nProcessing account: {account.name}")
        
        # Get balances
        actual_balance_cents = account.balance
        akahu_balance = get_akahu_balance(
            mapping_entry['akahu_id'],
            AKAHU_ENDPOINT,
            AKAHU_HEADERS
        )
        
        if akahu_balance is None:
            logging.error(f"Could not get Akahu balance for {account.name}")
            continue
            
        # Convert Akahu balance to cents
        akahu_balance_cents = int(decimal.Decimal(str(akahu_balance)) * 100)
        
        logging.info(f"Actual balance: ${actual_balance_cents/100:,.2f}")
        logging.info(f"Akahu balance: ${akahu_balance_cents/100:,.2f}")
        
        if akahu_balance_cents != actual_balance_cents:
            # Calculate adjustment
            adjustment_cents = akahu_balance_cents - actual_balance_cents
            
            transaction_date = datetime.utcnow().date()
            payee_name = "Balance Adjustment (Fixup)"
            notes = f"Adjusted from ${actual_balance_cents/100:,.2f} to ${akahu_balance_cents/100:,.2f}"
            
            create_transaction(
                actual.session,
                date=transaction_date,
                account=account.id,
                payee=payee_name,
                notes=notes,
                amount=adjustment_cents,
                imported_id=f"fixup_{datetime.utcnow().isoformat()}",
                cleared=True,
                imported_payee=payee_name
            )
            logging.info(f"Created adjustment of ${adjustment_cents/100:,.2f}")
        else:
            logging.info("No adjustment needed")

try:
    # Load mapping data
    mapping_data = load_mapping()
    
    # Connect to Actual
    with Actual(
        base_url=ENVs['ACTUAL_SERVER_URL'],
        password=ENVs['ACTUAL_PASSWORD'],
        file=ENVs['ACTUAL_SYNC_ID'],
        encryption_password=ENVs['ACTUAL_ENCRYPTION_KEY']
    ) as actual:
        logging.info("Successfully connected to Actual")
        
        # Download budget
        logging.info("Downloading budget...")
        actual.download_budget()
        
        # Fix balances
        fix_account_balances(actual, mapping_data)
        
        # Commit changes
        logging.info("\nCommitting changes...")
        actual.commit()
        
        logging.info("Done!")

except Exception as e:
    logging.error(f"Failed to process: {str(e)}")
    logging.error(f"Error type: {type(e)}")
    logging.error(f"Full traceback: {traceback.format_exc()}")
    raise