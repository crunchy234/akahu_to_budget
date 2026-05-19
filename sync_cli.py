"""CLI entrypoint for one-shot sync without importing Flask."""

import argparse
import logging
import signal
import sys

from modules.sync_runner import configure_logging, run_sync


def signal_handler(sig, frame):
    logging.info("Received signal to terminate. Shutting down gracefully...")
    sys.exit(0)


def main():
    configure_logging()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Perform direct sync.")
    parser.add_argument("--sync", action="store_true", help="Perform direct sync and exit.")
    parser.add_argument(
        "--accounts",
        help=(
            "Comma-separated list of Akahu account IDs to sync "
            "(e.g. acc_123,acc_456). If not provided, all accounts will be synced."
        ),
    )
    parser.add_argument(
        "--debug",
        nargs="?",
        const="all",
        help=(
            "Enable debug mode. Without parameter, prints Akahu IDs for all "
            "transactions. With parameter, treats it as an Akahu transaction ID "
            "and enables verbose debugging for that transaction."
        ),
    )
    args = parser.parse_args()

    account_ids = args.accounts.split(",") if args.accounts else None
    run_sync(account_ids, debug_mode=args.debug)


if __name__ == "__main__":
    main()
