"""Command line script for running transaction tests."""
import logging
import os
import sys
from actual import Actual
from dotenv import load_dotenv
from modules.transaction_tester import run_transaction_tests
from modules.account_mapper import load_existing_mapping

def disable_sqlalchemy_logging():
    """Completely disable SQLAlchemy logging."""
    logging.getLogger('sqlalchemy').setLevel(logging.CRITICAL)  # Suppress all SQLAlchemy logs

def setup_logging():
    """Configure logging for the test script."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[logging.StreamHandler()],
    )
    # Disable SQLAlchemy logs entirely
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
        'YNAB_BEARER_TOKEN',
        'YNAB_BUDGET_ID'
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
    
    # Set up YNAB headers and endpoint
    env_vars['ynab_headers'] = {'Authorization': f'Bearer {env_vars["YNAB_BEARER_TOKEN"]}'}
    env_vars['ynab_endpoint'] = 'https://api.ynab.com/v1/'
    
    return env_vars

def load_mapping():
    """Load account mapping configuration."""
    try:
        _, _, _, mapping_list = load_existing_mapping()
        return mapping_list
    except Exception as e:
        raise ValueError(f"Failed to load mapping: {str(e)}")

def main():
    """Main entry point for running tests."""
    try:
        setup_logging()
        logging.info("Starting transaction tests from command line")
        
        # Load environment variables
        env_vars = load_env_vars()
        
        # Load account mapping
        mapping_list = load_mapping()
        
        # Initialize Actual client using context manager
        with Actual(
            base_url=env_vars['ACTUAL_SERVER_URL'],
            password=env_vars['ACTUAL_PASSWORD'],
            file=env_vars['ACTUAL_SYNC_ID'],
            encryption_password=env_vars['ACTUAL_ENCRYPTION_KEY']
        ) as actual_client:
            # Run tests
            result = run_transaction_tests(actual_client, mapping_list, env_vars)
            logging.info(f"Test result: {result}")
        
    except Exception as e:
        logging.error(f"Error running tests: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
