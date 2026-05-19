#!/usr/bin/env python3
"""Export Actual Budget payee statistics for consolidation review."""

import json
import logging
import os
from collections import defaultdict
from actual import Actual
from actual.queries import get_transactions, get_categories
from dotenv import load_dotenv


def get_actual_env():
    """Load the Actual credentials needed by this standalone tool."""
    load_dotenv()
    required_envs = [
        'ACTUAL_SERVER_URL',
        'ACTUAL_PASSWORD',
        'ACTUAL_ENCRYPTION_KEY',
        'ACTUAL_SYNC_ID',
    ]
    envs = {key: os.getenv(key) for key in required_envs}
    missing = [key for key, value in envs.items() if value is None]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )
    return envs

def get_payee_data():
    """Extract payee data with transaction counts and categories."""
    envs = get_actual_env()
    with Actual(
        base_url=envs['ACTUAL_SERVER_URL'],
        password=envs['ACTUAL_PASSWORD'],
        file=envs['ACTUAL_SYNC_ID'],
        encryption_password=envs['ACTUAL_ENCRYPTION_KEY']
    ) as actual:
        actual.download_budget()
        transactions = get_transactions(actual.session)
        categories = get_categories(actual.session)
        
        # Create category lookup map
        category_lookup = {cat.id: cat.name for cat in categories}
        
        # Aggregate by payee
        payee_data = defaultdict(lambda: {
            'total_transactions': 0,
            'categories': {},
            'total_amount': 0
        })
        skipped_manual_transactions = 0
        
        for txn in transactions:
            # Only analyze transactions with imported_description since rules operate on imported data
            if txn.imported_description is None:
                skipped_manual_transactions += 1
                # Skip manual transactions - they don't need import rules
                continue
            if txn.imported_description == '':
                raise ValueError(f"Transaction {txn.id} has empty imported_description")
            payee = txn.imported_description
                
            if txn.category_id is None:
                category = "UNCATEGORISED"
            else:
                if txn.category_id not in category_lookup:
                    raise ValueError(f"Transaction {txn.id} references unknown category_id: {txn.category_id}")
                category = category_lookup[txn.category_id]
                
            if txn.amount is None:
                raise ValueError(f"Transaction missing amount: {txn.id}")
            amount = txn.amount
            
            payee_data[payee]['total_transactions'] += 1
            payee_data[payee]['total_amount'] += amount
            
            if category not in payee_data[payee]['categories']:
                payee_data[payee]['categories'][category] = 0
            payee_data[payee]['categories'][category] += 1

        if skipped_manual_transactions:
            logging.info(
                "Skipped %s transactions with no imported_description",
                skipped_manual_transactions,
            )
        
        return dict(payee_data)

def format_for_openai(payee_data):
    """Format payee data for OpenAI analysis."""
    # Sort by primary category first, then by transaction count within category
    def sort_key(item):
        payee, data = item
        primary_cat = max(data['categories'].items(), key=lambda x: x[1])[0] if data['categories'] else 'None'
        return (primary_cat, -data['total_transactions'])  # negative for descending order
    
    sorted_payees = sorted(payee_data.items(), key=sort_key)
    
    output = []
    output.append("PAYEE ANALYSIS FOR CONSOLIDATION")
    output.append("=" * 50)
    output.append(f"Total unique payees: {len(payee_data)}")
    output.append(f"Total transactions: {sum(p['total_transactions'] for p in payee_data.values())}")
    output.append("")
    output.append("Top payees by transaction count:")
    output.append("Rank | Txns | Amount    | Payee Name                          | Primary Category")
    output.append("-" * 85)
    
    for i, (payee, data) in enumerate(sorted_payees, 1):
        primary_cat = max(data['categories'].items(), key=lambda x: x[1])[0] if data['categories'] else 'None'
        amount = data['total_amount'] / 100  # Convert from cents
        output.append(f"{i:4d} | {data['total_transactions']:4d} | ${amount:8.2f} | {payee[:35]:<35} | {primary_cat[:20]}")
    
    return "\n".join(output)

def main():
    payee_data = get_payee_data()
    
    # Save raw data
    with open('payee_analysis_raw.json', 'w') as f:
        json.dump(payee_data, f, indent=2)
    
    # Format for OpenAI
    openai_format = format_for_openai(payee_data)
    
    # Save formatted data
    with open('payee_analysis_for_openai.txt', 'w') as f:
        f.write(openai_format)

if __name__ == "__main__":
    main()
