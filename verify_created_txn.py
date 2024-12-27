"""Command line script for debugging transaction visibility issues."""
import logging
import os
import sys
from datetime import datetime, timedelta
import decimal
from actual import Actual
from dotenv import load_dotenv
from sqlmodel import select
from actual.database import Transactions, Accounts
from actual.queries import get_transactions, create_transaction

from modules.transaction_tester import run_transaction_tests
from modules.account_mapper import load_existing_mapping

def disable_sqlalchemy_logging():
    """Completely disable SQLAlchemy logging."""
    logging.getLogger('sqlalchemy').setLevel(logging.CRITICAL)

def setup_logging():
    """Configure logging for the test script."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[logging.StreamHandler()],
    )
    disable_sqlalchemy_logging()
    logging.getLogger('urllib3').setLevel(logging.INFO)

def load_env_vars():
    """Load required environment variables."""
    load_dotenv()
    
    required_vars = [
        'ACTUAL_SERVER_URL',
        'ACTUAL_PASSWORD',
        'ACTUAL_ENCRYPTION_KEY',
        'ACTUAL_SYNC_ID',
    ]
    
    env_vars = {}
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value is None:
            missing_vars.append(var)
        env_vars[var] = value
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    return env_vars

def verify_transaction_visibility(actual_client, transaction_id=None):
    """Comprehensive verification of transaction visibility."""
    logger = logging.getLogger(__name__)
    logger.info("\n=== Transaction Visibility Debug ===")

    try:
        # First check if we can find the specific transaction
        if transaction_id:
            logger.info(f"Looking for specific transaction: {transaction_id}")
            with actual_client.session as session:
                # Direct database query
                query = select(Transactions).filter(
                    Transactions.id == transaction_id,
                    Transactions.tombstone == 0
                )
                transaction = session.exec(query).first()
                
                if transaction:
                    logger.info("Found transaction in direct database query:")
                    logger.info(f"ID: {transaction.id}")
                    logger.info(f"Amount: {transaction.amount/100}")
                    logger.info(f"Account ID: {transaction.acct}")
                    logger.info(f"Date: {transaction.date}")
                    logger.info(f"Tombstone: {transaction.tombstone}")
                    logger.info(f"Is Parent: {transaction.is_parent}")
                    logger.info(f"Is Child: {transaction.is_child}")
                    
                    # Check account details
                    account_query = select(Accounts).filter(Accounts.id == transaction.acct)
                    account = session.exec(account_query).first()
                    if account:
                        logger.info("\nAccount details:")
                        logger.info(f"Name: {account.name}")
                        logger.info(f"Off Budget: {account.offbudget}")
                        logger.info(f"Closed: {account.closed}")
                        logger.info(f"Tombstone: {account.tombstone}")
                else:
                    logger.error("Transaction not found in direct database query!")

        # Check recent transactions via the API
        logger.info("\nChecking recent transactions via get_transactions:")
        actual_client.download_budget()  # Ensure we have latest data
        
        with actual_client.session as session:
            # Get transactions from the last 7 days
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)
            
            recent_transactions = get_transactions(
                session,
                start_date=start_date,
                end_date=end_date + timedelta(days=1)
            )
            
            logger.info(f"\nFound {len(recent_transactions)} transactions in the last 7 days:")
            for txn in recent_transactions:
                logger.info(
                    f"ID: {txn.id}, "
                    f"Date: {txn.date}, "
                    f"Amount: ${txn.amount/100:.2f}, "
                    f"Description: {txn.imported_description}"
                )

        logger.info("\n=== Verification Complete ===")

    except Exception as e:
        logger.error(f"Error during verification: {str(e)}", exc_info=True)

def create_test_transaction(actual_client):
    """Create a test transaction for debugging."""
    logger = logging.getLogger(__name__)
    logger.info("\n=== Creating Test Transaction ===")
    
    with actual_client.session as session:
        # Get the first active account
        account = session.exec(
            select(Accounts)
            .filter(Accounts.closed == 0, Accounts.tombstone == 0)
        ).first()
        
        if not account:
            logger.error("No active accounts found!")
            return None
        
        logger.info(f"Using account: {account.name} (ID: {account.id})")
        
        # Create a test transaction
        test_amount = decimal.Decimal("-10.00")
        test_date = datetime.now().date()
        
        # Create the transaction
        transaction = create_transaction(
            session,
            date=test_date,
            account=account.id,
            payee="Debug Test Transaction",
            notes="Created for visibility debugging",
            amount=test_amount
        )
        
        # Log pre-commit state
        logger.info("Transaction created, pre-commit state:")
        logger.info(f"Transaction in session: {bool(transaction in session)}")
        logger.info(f"Transaction state: {vars(transaction)}")
        
        # Explicitly commit
        try:
            session.commit()
            logger.info("Session committed successfully")
            
            # Verify immediately after commit
            session.refresh(transaction)
            logger.info("Transaction refreshed from database")
            logger.info(f"Post-commit state: {vars(transaction)}")
            
            # Verify it's in the database
            verify_txn = session.exec(
                select(Transactions)
                .filter(Transactions.id == transaction.id)
            ).first()
            logger.info(f"Found in database after commit: {bool(verify_txn)}")
            
        except Exception as e:
            logger.error(f"Commit failed: {str(e)}", exc_info=True)
            session.rollback()
            raise
        
        logger.info(f"Created test transaction: {transaction.id}")
        return transaction.id
        

def main():
    """Main entry point for running debug checks."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("StarExceptionting transaction visibility debug")
    
    # Load environment variables
    env_vars = load_env_vars()
    
    # Initialize Actual client using context manager
    with Actual(
        server_url=env_vars['ACTUAL_SERVER_URL'],
        password=env_vars['ACTUAL_PASSWORD'],
        budget_id=env_vars['ACTUAL_SYNC_ID'],
        encryption_password=env_vars['ACTUAL_ENCRYPTION_KEY']
    ) as actual_client:
        # Force initial sync
        logger.info("Performing initial budget download...")
        sync_result = actual_client.download_budget()
        logger.info(f"Initial sync result: {sync_result}")

        # First create a test transaction
        test_transaction_id = create_test_transaction(actual_client)
        if test_transaction_id:
            logger.info(f"Created test transaction with ID: {test_transaction_id}")
            
            # Verify the test transaction
            verify_transaction_visibility(actual_client, test_transaction_id)
            
            # Also check for your specific transaction ID if provided
            if len(sys.argv) > 1:
                specific_transaction_id = sys.argv[1]
                logger.info(f"\nChecking specific transaction: {specific_transaction_id}")
                verify_transaction_visibility(actual_client, specific_transaction_id)
        else:
            logger.error("Failed to create test transaction!")
        

if __name__ == '__main__':
    main()