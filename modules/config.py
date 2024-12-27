"""Module for handling configuration and environment variables."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

required_envs = [
    'ACTUAL_SERVER_URL',
    'ACTUAL_PASSWORD',
    'ACTUAL_ENCRYPTION_KEY',
    'ACTUAL_SYNC_ID',
    'AKAHU_USER_TOKEN',
    'AKAHU_APP_TOKEN',
    'AKAHU_PUBLIC_KEY',
    "YNAB_BEARER_TOKEN",
]

# Load environment variables into a dictionary for validation
ENVs = {key: os.getenv(key) for key in required_envs}

# Validate environment variables
for key, value in ENVs.items():
    if value is None:
        raise EnvironmentError(f"Missing required environment variable: {key}")

# API endpoints and headers
YNAB_ENDPOINT = "https://api.ynab.com/v1/"
YNAB_HEADERS = {"Authorization": f"Bearer {ENVs['YNAB_BEARER_TOKEN']}"}

AKAHU_ENDPOINT = "https://api.akahu.io/v1/"
AKAHU_HEADERS = {
    "Authorization": f"Bearer {ENVs['AKAHU_USER_TOKEN']}",
    "X-Akahu-ID": ENVs['AKAHU_APP_TOKEN']
}