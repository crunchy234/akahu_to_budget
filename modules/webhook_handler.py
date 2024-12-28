"""Module for handling webhook operations and Flask app creation."""
import base64
import logging
from flask import Flask, request, jsonify, redirect, url_for
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
# from cryptography.exceptions import InvalidSignature # Currently unused
import pandas as pd

from modules.account_mapper import load_existing_mapping
from modules.config import RUN_SYNC_TO_AB, RUN_SYNC_TO_YNAB
from modules.sync_handler import sync_to_ab, sync_to_ynab
from modules.sync_status import generate_sync_report
from modules.transaction_handler import load_transactions_into_actual
from modules.transaction_tester import run_transaction_tests

def verify_signature(public_key: str, signature: str, request_body: bytes) -> None:
    """Verify that the request body has been signed by Akahu."""
    public_key = serialization.load_pem_public_key(public_key.encode('utf-8'))
    public_key.verify(
        base64.b64decode(signature),
        request_body,
        padding.PKCS1v15(),
        hashes.SHA256()
    )

def create_flask_app(actual_client, mapping_list, env_vars):
    """Create and configure Flask application for webhook handling."""
    app = Flask(__name__)

    @app.route('/test', methods=['GET'])
    def test_transactions():
        """Test endpoint to validate transaction handling."""
        try:
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
            akahu_accounts, actual_accounts, ynab_accounts, _ = load_existing_mapping()

            if RUN_SYNC_TO_AB:
                actual_client.download_budget()
                
            for akahu_account_id, mapping_entry in mapping_list.items():
                try:
                    if RUN_SYNC_TO_AB:
                        if not mapping_entry.get('actual_do_not_map') and mapping_entry.get('actual_account_id'):
                            actual_count += sync_to_ab(actual_client, mapping_list)

                    if RUN_SYNC_TO_YNAB:
                        if not mapping_entry.get('ynab_do_not_map') and mapping_entry.get('ynab_account_id'):
                            ynab_count += sync_to_ynab(mapping_list)

                except Exception as e:
                    error_msg = f"Error processing account {akahu_account_id}: {str(e)}"
                    logging.error(error_msg)
                    errors.append(error_msg)

            return generate_sync_report(mapping_list, actual_count, ynab_count, errors)

        except Exception as e:
            logging.error(f"Sync failed: {str(e)}")
            return jsonify({
                "status": "error",
                "error": str(e),
            }), 500
    
    @app.route('/status', methods=['GET'])
    def status():
        """Endpoint to check if the webhook server is running."""
        return jsonify({"status": "Webhook server is running"}), 200

    @app.route('/receive-transaction', methods=['POST'])
    def receive_transaction():
        """Handle incoming webhook events from Akahu."""
        if not RUN_SYNC_TO_AB:
            raise NotImplementedError("Webhook sync to YNAB not implemented")

        signature = request.headers.get("X-Akahu-Signature")
        verify_signature(env_vars['AKAHU_PUBLIC_KEY'], signature, request.data)

        data = request.get_json()
        if data["type"] != "TRANSACTION_CREATED":
            return jsonify({"status": "ignored - not a transaction event"}), 200

        transactions = data["item"]
        akahu_account_id = transactions['account']['_id']
        mapping_entry = mapping_list[akahu_account_id]
            
        if mapping_entry.get('actual_do_not_map'):
            return jsonify({"status": "skipped - do not map"}), 200

        actual_client.download_budget()
        load_transactions_into_actual(
            pd.DataFrame([transactions]),
            mapping_entry,
            actual_client
        )
        return jsonify({"status": "success"}), 200

    return app

def start_webhook_server(app, development_mode=False):
    """Start the Flask webhook server."""
    app.run(host="0.0.0.0", port=5000, debug=development_mode)