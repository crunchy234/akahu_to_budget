"""Module for handling configuration and environment variables."""

import os
import logging
from dotenv import load_dotenv

# Load environment variables with override=True to ensure .env values are used
load_dotenv(verbose=True, override=True)


def getenv_stripped(key, default=None):
    """Get an environment variable with surrounding quotes stripped.

    python-dotenv strips quotes when loading .env files, but Docker's
    --env-file passes them literally.  This helper normalises both sources.
    """
    val = os.getenv(key, default)
    if isinstance(val, str):
        val = val.strip().strip('"').strip("'")
    return val

for flag in ("RUN_SYNC_TO_YNAB", "RUN_SYNC_TO_AB"):
    if getenv_stripped(flag) is None:
        raise EnvironmentError(f"Missing required environment variable: {flag}")

RUN_SYNC_TO_YNAB = getenv_stripped("RUN_SYNC_TO_YNAB").lower() == "true"
RUN_SYNC_TO_AB = getenv_stripped("RUN_SYNC_TO_AB").lower() == "true"
FORCE_REFRESH = getenv_stripped("FORCE_REFRESH", "false").lower() == "true"
DEBUG_SYNC = getenv_stripped("DEBUG_SYNC", "false").lower() == "true"

if not RUN_SYNC_TO_YNAB and not RUN_SYNC_TO_AB:
    logging.error(
        "Environment variable RUN_SYNC_TO_YNAB or RUN_SYNC_TO_AB must be True."
    )
    raise EnvironmentError(
        "Environment variable RUN_SYNC_TO_YNAB or RUN_SYNC_TO_AB must be True."
    )

required_envs = ["AKAHU_USER_TOKEN", "AKAHU_APP_TOKEN"]
if RUN_SYNC_TO_AB:
    required_envs += [
        "ACTUAL_SERVER_URL",
        "ACTUAL_PASSWORD",
        "ACTUAL_ENCRYPTION_KEY",
        "ACTUAL_SYNC_ID",
    ]
if RUN_SYNC_TO_YNAB:
    required_envs += ["YNAB_BEARER_TOKEN"]

ENVs = {key: getenv_stripped(key) for key in required_envs}

for key, value in ENVs.items():
    if value is None:
        raise EnvironmentError(f"Missing required environment variable: {key}")

AKAHU_ENDPOINT = "https://api.akahu.io/v1"
AKAHU_HEADERS = {
    "Authorization": f"Bearer {ENVs['AKAHU_USER_TOKEN']}",
    "X-Akahu-ID": ENVs["AKAHU_APP_TOKEN"],
}

YNAB_ENDPOINT = "https://api.ynab.com/v1/"
YNAB_HEADERS = (
    {"Authorization": f"Bearer {ENVs['YNAB_BEARER_TOKEN']}"}
    if RUN_SYNC_TO_YNAB
    else None
)
