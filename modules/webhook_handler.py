"""Module for handling webhook operations and Flask app creation."""
import base64
import logging
import pandas as pd
from flask import Flask, request, jsonify, redirect, url_for
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from threading import Thread

from .transaction_handler import load_transactions_into_actual, get_all_akahu

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

    @app.route('/')
    def root():
        """Root endpoint redirects to status."""
        return redirect(url_for('status'))

    @app.route('/sync', methods=['GET'])
    def run_full_sync():
        """Endpoint to run a full sync of all accounts."""
        actual_client.download_budget()
        logging.info("Budget downloaded successfully for full sync.")
        for akahu_account_id, mapping_entry in mapping_list.items():
            if mapping_entry.get('actual_do_not_map'):
                logging.warning(
                    f"Skipping sync to Actual Budget for Akahu account {akahu_account_id}: because this account is configured to not be mapped to Actual Budget."
                )
                continue
                
            if mapping_entry.get('actual_account_id'):
                last_reconciled_at = mapping_entry.get('actual_synced_datetime', '2024-01-01T00:00:00Z')
                akahu_df = get_all_akahu(
                    akahu_account_id,
                    env_vars['akahu_endpoint'],
                    env_vars['akahu_headers'],
                    last_reconciled_at
                )
                if akahu_df is not None and not akahu_df.empty:
                    load_transactions_into_actual(akahu_df, mapping_entry, actual_client)
            else:
                logging.warning(
                    f"Skipping sync to Actual Budget for Akahu account {akahu_account_id}: Missing Actual Budget IDs."
                )
        return jsonify({"status": "full sync complete"}), 200

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
        app.run(host="0.0.0.0", port=5000, debug=True)
    else:
        flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=5000))
        flask_thread.daemon = True
        flask_thread.start()
        logging.info("Webhook server started and running.")