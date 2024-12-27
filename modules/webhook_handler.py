"""Module for handling webhook operations and Flask app creation."""
import base64
import logging
import json
import pandas as pd
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from threading import Thread
from actual.queries import get_transactions

from modules.account_mapper import load_existing_mapping
from modules.sync_handler import sync_to_ab, sync_to_ynab
from modules.sync_status import generate_sync_report

from .transaction_handler import (
    load_transactions_into_actual,
    get_all_akahu,
    clean_txn_for_ynab,
    load_transactions_into_ynab
)

def verify_signature(public_key: str, signature: str, request_body: bytes) -> None:
    """Verify that the request body has been signed by Akahu."""
    try:
        public_key = serialization.load_pem_public_key(public_key.encode('utf-8'))
        public_key.verify(
            base64.b64decode(signature),
            request_body,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        logging.info("Webhook verification succeeded. This webhook is from Akahu!")
    except InvalidSignature:
        logging.error("Invalid webhook caller. Verification failed!")
        raise InvalidSignature("Invalid signature for webhook request")

def create_flask_app(actual_client, mapping_list, env_vars):
    """Create and configure Flask application for webhook handling."""
    app = Flask(__name__)

    @app.route('/test', methods=['GET'])
    def test_transactions():
        """Test endpoint to validate transaction handling."""
        try:
            from .transaction_tester import run_transaction_tests
            result = run_transaction_tests(actual_client, mapping_list, env_vars)
            return jsonify(result), 200
        except Exception as e:
            logging.error(f"\n=== Test Failed ===\nError in test endpoint: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/')
    def root():
        """Root endpoint redirects to status."""
        return redirect(url_for('status'))


    @app.route('/sync', methods=['GET'])
    def run_full_sync():
        """Run a full sync of all accounts."""
        errors = []
        actual_count = 0
        ynab_count = 0
        
        try:
            # Download latest budget state
            actual_client.download_budget()
            logging.info("Budget downloaded successfully for full sync")
            akahu_accounts, actual_accounts, ynab_accounts, _ = load_existing_mapping()

            # Process each account
            for akahu_account_id, mapping_entry in mapping_list.items():
                try:
                    # Process Actual Budget sync
                    if not mapping_entry.get('actual_do_not_map') and mapping_entry.get('actual_account_id'):
                        actual_count += sync_to_ab(actual_client, mapping_list, akahu_accounts, actual_accounts, ynab_accounts)

                    # Process YNAB sync
                    if not mapping_entry.get('ynab_do_not_map') and mapping_entry.get('ynab_account_id'):
                        ynab_count += sync_to_ynab(mapping_list)

                except Exception as e:
                    error_msg = f"Error processing account {akahu_account_id}: {str(e)}"
                    logging.error(error_msg)
                    errors.append(error_msg)

            # Generate detailed sync report
            return generate_sync_report(mapping_list, actual_count, ynab_count, errors)

        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            logging.error(error_msg)
            return jsonify({
                "status": "error",
                "error": error_msg,
            }), 500
    
    @app.route('/status', methods=['GET'])
    def status():
        """Endpoint to check if the webhook server is running."""
        return jsonify({"status": "Webhook server is running"}), 200

    @app.route('/receive-transaction', methods=['POST'])
    def receive_transaction():
        """Handle incoming webhook events from Akahu."""
        signature = request.headers.get("X-Akahu-Signature")
        request_body = request.data
        try:
            verify_signature(env_vars['AKAHU_PUBLIC_KEY'], signature, request_body)
        except InvalidSignature:
            return jsonify({"status": "invalid signature"}), 400

        data = request.get_json()
        if data and "type" in data and data["type"] == "TRANSACTION_CREATED":
            transactions = data.get("item", [])
            akahu_account_id = transactions.get('account', {}).get('_id')
            mapping_entry = mapping_list.get(akahu_account_id)
            
            if mapping_entry and mapping_entry.get('actual_do_not_map'):
                logging.warning(
                    f"Skipping webhook transaction sync to Actual Budget for Akahu account {akahu_account_id}: because this account is configured to not be mapped to Actual Budget."
                )
                return jsonify({"status": "skipped - do not map"}), 200
                
            actual_client.download_budget()
            logging.info("Budget downloaded successfully for webhook event.")
            
            if mapping_entry and mapping_entry.get('actual_account_id'):
                load_transactions_into_actual(
                    pd.DataFrame([transactions]),
                    mapping_entry,
                    actual_client
                )
                return jsonify({"status": "success"}), 200
            else:
                logging.warning(
                    f"Skipping webhook transaction sync to Actual Budget for Akahu account {akahu_account_id}: Missing Actual Budget IDs."
                )
                return jsonify({"status": "skipped - missing ids"}), 200
            
        logging.info("/receive-transaction endpoint ignored as it is not a TRANSACTION_CREATED event.")
        return jsonify({"status": "ignored"}), 200

    return app

def start_webhook_server(app, development_mode=False):
    """Start the Flask webhook server."""
    if development_mode:
        # In development mode, run with Flask's built-in reloader
        app.run(host="0.0.0.0", port=5000, debug=True)
    else:
        # In production mode, run in a daemon thread that can be interrupted
        def run_server():
            try:
                app.run(host="0.0.0.0", port=5000)
            except KeyboardInterrupt:
                logging.info("Webhook server shutting down...")
                
        flask_thread = Thread(target=run_server)
        flask_thread.daemon = True
        flask_thread.start()
        logging.info("Webhook server started and running.")