import os
import sys
import sqlite3
import argparse
from pathlib import Path
import decimal
from actual import Actual
from modules.config import ENVs
from datetime import datetime

# Debug script
# Run python search_transaction.py --refresh to copy your budget to this folder
# Run python .\search_transaction.py 1234.56 to find a transaction of an exact amount.
# 
# So for example 
# 1. Remove the transfer in Actual Budget
# 2. Run python .\flask_app.py --sync to create it
# At this point, both sides of the transfer should exist... but maybe they don't
# 3. Run search_transaction.py --refresh to get the local database up to date
# 4. Run search_transaction.py 1234.56 to scan the database for any transactions in any account for this amount.

def refresh_database():
    """Download a fresh copy of the database."""
    data_dir = Path('actual-budget-data')
    data_dir.mkdir(exist_ok=True)
    
    print("Downloading fresh copy of database...")
    with Actual(
        base_url=ENVs['ACTUAL_SERVER_URL'],
        password=ENVs['ACTUAL_PASSWORD'],
        file=ENVs['ACTUAL_SYNC_ID'],
        encryption_password=ENVs['ACTUAL_ENCRYPTION_KEY'],
        data_dir=data_dir
    ) as actual:
        actual.download_budget()
    print("Database downloaded successfully")

def format_sort_order(sort_order):
    """
    Convert sort_order (milliseconds since epoch) to a readable date string.
    Returns None if conversion fails.
    """
    if not sort_order:
        return None
    try:
        # Convert milliseconds to seconds for timestamp
        timestamp = float(sort_order) / 1000
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError, TypeError):
        return f"Raw value: {sort_order}"

def search_transactions_by_amount(amount):
    """
    Search for transactions in Actual Budget by amount using direct SQL.
    
    Args:
        amount (float): The amount to search for in dollars
        
    Returns:
        list: List of matching transactions
    """
    # Convert dollars to cents since that's how it's stored in the database
    amount_cents = int(decimal.Decimal(str(amount)) * 100)
    
    # Use a persistent data directory in the current folder
    data_dir = Path('actual-budget-data')
    db_path = data_dir / 'db.sqlite'
    
    if not db_path.exists():
        print("Error: Database not found. Please run with --refresh to download it.")
        return []
    
    # Connect directly to the SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Query transactions with joins to get related data
    query = """
    SELECT 
        t.id,
        t.date,
        t.amount,
        t.notes,
        t.financial_id,
        t.imported_description,
        t.cleared,
        t.reconciled,
        t.pending,
        t.isChild,
        t.isParent,
        t.sort_order,
        t.transferred_id,
        t.parent_id,
        t.type,
        t.error,
        p.name as payee_name,
        c.name as category_name,
        a.name as account_name,
        -- Get the linked transfer's account name if this is a transfer
        a2.name as transfer_account_name
    FROM transactions t
    LEFT JOIN payees p ON t.description = p.id
    LEFT JOIN categories c ON t.category = c.id
    LEFT JOIN accounts a ON t.acct = a.id
    -- Join with transactions and accounts again to get transfer details
    LEFT JOIN transactions t2 ON t.transferred_id = t2.id
    LEFT JOIN accounts a2 ON t2.acct = a2.id
    WHERE t.amount = ? AND t.tombstone = 0
    ORDER BY t.date DESC
    """
    
    cursor.execute(query, (amount_cents,))
    results = []
    
    for row in cursor.fetchall():
        # Convert date from YYYYMMDD format to YYYY-MM-DD
        date_str = str(row[1])
        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        
        results.append({
            'id': row[0],
            'dates': {
                'transaction': formatted_date,
                'created': format_sort_order(row[11])
            },
            'amount': float(row[2]) / 100,  # Convert cents to dollars
            'notes': row[3],
            'financial_id': row[4],
            'original_description': row[5],
            'status': {
                'cleared': bool(row[6]),
                'reconciled': bool(row[7]),
                'pending': bool(row[8])
            },
            'split': {
                'is_child': bool(row[9]),
                'is_parent': bool(row[10]),
                'parent_id': row[13]  # Link to parent transaction if this is a split
            },
            'transfer': {
                'id': row[12],  # ID of the other side of the transfer
                'account': row[19]  # Name of the account for the other side
            },
            'type': row[14],
            'error': row[15],
            'payee': row[16],
            'category': row[17],
            'account': row[18]
        })
    
    conn.close()
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Search Actual Budget transactions by amount')
    parser.add_argument('amount', type=float, nargs='?', help='Amount to search for (e.g., 42.50)')
    parser.add_argument('--refresh', action='store_true', help='Download a fresh copy of the database before searching')
    
    args = parser.parse_args()
    
    if args.refresh:
        refresh_database()
    
    if args.amount is None:
        parser.print_help()
        sys.exit(1)
    
    results = search_transactions_by_amount(args.amount)
    
    if results:
        print(f"\nFound {len(results)} transaction(s):")
        for i, result in enumerate(results, 1):
            print(f"\nTransaction {i}:")
            print(f"ID: {result['id']}")
            print("Dates:")
            print(f"  - Transaction: {result['dates']['transaction']}")
            print(f"  - Created: {result['dates']['created']}")
            print(f"Amount: ${result['amount']:,.2f}")
            print(f"Account: {result['account']}")
            print(f"Type: {result['type'] or 'None'}")
            if result['error']:
                print(f"Error: {result['error']}")
            
            # Show transfer information if this is a transfer
            if result['transfer']['id']:
                print("Transfer Details:")
                print(f"  - Other Side ID: {result['transfer']['id']}")
                print(f"  - Other Account: {result['transfer']['account']}")
            
            # Show split information if this is part of a split
            if result['split']['is_child']:
                print(f"Split Child (Parent ID: {result['split']['parent_id']})")
            elif result['split']['is_parent']:
                print("Split Parent")
            
            print(f"Payee: {result['payee']}")
            print(f"Category: {result['category']}")
            print(f"Notes: {result['notes']}")
            print(f"Original Description: {result['original_description']}")
            print(f"Financial ID: {result['financial_id']}")
            print("Status:")
            print(f"  - Cleared: {result['status']['cleared']}")
            print(f"  - Reconciled: {result['status']['reconciled']}")
            print(f"  - Pending: {result['status']['pending']}")
    else:
        print(f"\nNo transactions found with amount ${args.amount:,.2f}")