# THis script is responsible for reading from Akahu, Actual Budget and YNAB
# ANd creating a mapping JSON
#
# It's also handy because it acts as a sanity test of the APIs
# If this works then you know that connecting to all three is working, and there's no risk of breaking your budgets.

import datetime

import os
import pathlib
import logging
import json
import sys
from datetime import datetime

# Interactive matching of accounts
from fuzzywuzzy import process

import requests
from dotenv import load_dotenv
from actual import Actual
from actual.queries import (
    get_accounts,
)
import openai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Load environment variables from the parent directory's .env file
load_dotenv(dotenv_path=pathlib.Path(__file__).parent / '.env')

required_envs = [
    'ACTUAL_SERVER_URL',
    'ACTUAL_PASSWORD',
    'ACTUAL_ENCRYPTION_KEY',
    'ACTUAL_SYNC_ID',
    'AKAHU_USER_TOKEN',
    'AKAHU_APP_TOKEN',
    'AKAHU_PUBLIC_KEY',
    'OPENAI_API_KEY',
    "YNAB_BEARER_TOKEN",
]

# Load environment variables into a dictionary for validation
ENVs = {key: os.getenv(key) for key in required_envs}
SYNC_TO_YNAB = True
SYNC_TO_AB = True

# Validate that all environment variables are loaded
for key, value in ENVs.items():
    if value is None:
        logging.error(f"Environment variable {key} is missing.")
        raise EnvironmentError(f"Missing required environment variable: {key}")

client = openai.OpenAI(api_key=ENVs['OPENAI_API_KEY'])

ynab_endpoint = "https://api.ynab.com/v1/"
ynab_headers = {"Authorization": "Bearer " + ENVs['YNAB_BEARER_TOKEN']}

# Akahu API setup
akahu_endpoint = "https://api.akahu.io/v1/"
akahu_headers = {
    "Authorization": "Bearer " + ENVs['AKAHU_USER_TOKEN'],
    "X-Akahu-ID": ENVs['AKAHU_APP_TOKEN'],
}


# Load existing mapping from a JSON file
def load_existing_mapping(mapping_file="akahu_budget_mapping.json"):
    if pathlib.Path(mapping_file).exists():
        with open(mapping_file, "r") as f:
            data = json.load(f)
            akahu_accounts = data.get('akahu_accounts', {})
            actual_accounts = data.get('actual_accounts', {})
            ynab_accounts = data.get('ynab_accounts', {})
            mapping = data.get('mapping', {})
            # Convert mapping if it's in the old list format
            if isinstance(mapping, list):
                mapping = {entry['akahu_id']: entry for entry in mapping if 'akahu_id' in entry}
            return akahu_accounts, actual_accounts, ynab_accounts, mapping
    return {}, {}, {}, {}

def is_simple_value(value):
    # Check if the value is a trivial type: int, float, str, bool, or None
    return isinstance(value, (int, float, str, bool)) or value is None

def shallow_compare_dicts(dict1, dict2):
    # Filter out only the simple values from both dictionaries
    dict1_filtered = {k: v for k, v in dict1.items() if is_simple_value(v)}
    dict2_filtered = {k: v for k, v in dict2.items() if is_simple_value(v)}

    # Compare filtered versions
    return dict1_filtered == dict2_filtered

def fetch_ynab_accounts():
    logging.info("Fetching YNAB accounts...")
    try:
        ynab_budget_id = os.getenv("YNAB_BUDGET_ID")
        if not ynab_budget_id:
            raise ValueError("YNAB_BUDGET_ID environment variable is not set.")

        accounts_json = requests.get(f"{ynab_endpoint}budgets/{ynab_budget_id}/accounts", headers=ynab_headers).json()
        ynab_accounts = {}
        for account in accounts_json.get("data", {}).get("accounts", []):
            if not account.get("closed", False):
                ynab_accounts[account["id"]] = {
                    key: value for key, value in account.items() if is_simple_value(value)
                }
        logging.info(f"Fetched {len(ynab_accounts)} YNAB accounts for budget {ynab_budget_id}.")
        return ynab_accounts
    except Exception as e:
        logging.error(f"Failed to fetch YNAB accounts: {e}")
        return {}

def fetch_actual_accounts(actual_client):
    """Fetch accounts from Actual Budget if enabled."""
    try:
        # Download the budget
        actual_client.download_budget()
        logging.info("Budget downloaded successfully.")

        # Fetch Actual Budget accounts and convert to dictionary
        latest_actual_accounts = get_accounts(actual_client.session)
        open_actual_accounts = {
            acc.id: {key: value for key, value in acc.__dict__.items() if
                     not callable(value) and not key.startswith('_') and is_simple_value(value)}
            for acc in latest_actual_accounts if not acc.closed
        }
        logging.info(f"Fetched {len(open_actual_accounts)} open Actual accounts.")
        return open_actual_accounts
    except Exception as e:
        logging.error(f"Failed to fetch Actual accounts: {e}")
        raise

def combine_accounts(latest_accounts, existing_accounts):
    """
    Combines latest and existing accounts, preserving date_first_loaded.
    Now handles accounts as dictionaries instead of lists.
    """
    current_date = datetime.now().isoformat()
    combined_accounts = {}
    deleted_accounts = []

    # Convert latest_accounts list to dictionary if it's not already
    if isinstance(latest_accounts, list):
        latest_accounts = {acc['id']: acc for acc in latest_accounts}

    # Convert existing_accounts list to dictionary if it's not already
    if isinstance(existing_accounts, list):
        existing_accounts = {acc['id']: acc for acc in existing_accounts}

    # Merge latest and existing accounts
    for account_id, account_data in latest_accounts.items():
        if account_id in existing_accounts:
            # Preserve date_first_loaded from existing account
            account_data['date_first_loaded'] = existing_accounts[account_id].get('date_first_loaded', current_date)
        else:
            # New account, set date_first_loaded to current date
            account_data['date_first_loaded'] = current_date
        combined_accounts[account_id] = account_data

    # Identify accounts to delete
    for account_id in existing_accounts:
        if account_id not in latest_accounts:
            deleted_accounts.append(account_id)

    return combined_accounts, deleted_accounts


def merge_and_update_mapping(existing_mapping, latest_akahu_accounts, latest_actual_accounts, latest_ynab_accounts, existing_akahu_accounts, existing_actual_accounts, existing_ynab_accounts):
    """
    Merges and updates the account mapping to ensure consistency between Akahu, Actual, and YNAB accounts.

    :param existing_mapping: The current mapping of Akahu to Actual and/or YNAB accounts.
    :param latest_akahu_accounts: The latest Akahu accounts fetched from Akahu API (as a dictionary of dictionaries).
    :param latest_actual_accounts: The latest Actual accounts fetched from Actual API (as a dictionary of dictionaries).
    :param latest_ynab_accounts: The latest YNAB accounts fetched from YNAB API (as a dictionary of dictionaries).
    :param existing_akahu_accounts: Existing Akahu accounts in the mapping (as a dictionary of dictionaries).
    :param existing_actual_accounts: Existing Actual accounts in the mapping (as a dictionary of dictionaries).
    :param existing_ynab_accounts: Existing YNAB accounts in the mapping (as a dictionary of dictionaries).
    :return: Updated mapping, akahu accounts, actual accounts, and ynab accounts.
    """
    # Step 1: Combine Akahu Accounts
    combined_akahu_accounts, deleted_akahu_accounts = combine_accounts(latest_akahu_accounts, existing_akahu_accounts)

    # Step 2: Combine Actual Accounts
    combined_actual_accounts, deleted_actual_accounts = combine_accounts(latest_actual_accounts, existing_actual_accounts)

    # Step 3: Combine YNAB Accounts
    combined_ynab_accounts, deleted_ynab_accounts = combine_accounts(latest_ynab_accounts, existing_ynab_accounts)

    # Step 4: Create Updated Mapping
    # Report number of deleted accounts to the user
    if deleted_akahu_accounts:
        logging.info(f"{len(deleted_akahu_accounts)} Akahu accounts will be deleted.")
    if deleted_actual_accounts:
        logging.info(f"{len(deleted_actual_accounts)} Actual accounts will be deleted.")
    if deleted_ynab_accounts:
        logging.info(f"{len(deleted_ynab_accounts)} YNAB accounts will be deleted.")
    updated_mapping = existing_mapping.copy()

    # Step 5: Identify Accounts to be Deleted and Update Mapping
    akahu_to_delete = []
    actual_to_delete = []
    ynab_to_delete = []
    for akahu_id in list(updated_mapping.keys()):
        # Identify Akahu accounts that no longer exist
        if akahu_id not in combined_akahu_accounts:
            akahu_to_delete.append(akahu_id)
            continue

        # Identify Actual accounts that no longer exist if Actual is available and not empty
        # Always present even if empty, no need for this check
            actual_id = updated_mapping[akahu_id].get("actual_account_id")
            if actual_id and actual_id not in combined_actual_accounts:
                actual_to_delete.append((actual_id, akahu_id))

        # Identify YNAB accounts that no longer exist if YNAB is available and not empty
        # Always present even if empty, no need for this check
            ynab_id = updated_mapping[akahu_id].get("ynab_account_id")
            if ynab_id and ynab_id not in combined_ynab_accounts:
                ynab_to_delete.append((ynab_id, akahu_id))

    # Step 6: Report to User and Get Confirmation
    if akahu_to_delete or actual_to_delete or ynab_to_delete:
        logging.info("Summary of accounts to be deleted:")
        if akahu_to_delete:
            logging.info(f"{len(akahu_to_delete)} Akahu accounts to delete.")
        if actual_to_delete:
            logging.info(f"{len(actual_to_delete)} Actual accounts to delete.")
        if ynab_to_delete:
            logging.info(f"{len(ynab_to_delete)} YNAB accounts to delete.")

        confirmation = input("Do you want to proceed with deleting these accounts? (Y to confirm):")
        if confirmation.lower() == 'y':
            # Step 7: Delete Accounts as Confirmed
            for akahu_id in akahu_to_delete:
                updated_mapping.pop(akahu_id, None)
                logging.info(f"Deleted Akahu account with ID {akahu_id}.")
            for actual_id, akahu_id in actual_to_delete:
                if updated_mapping[akahu_id].get('actual_account_id') == actual_id:
                    updated_mapping[akahu_id].pop('actual_account_id', None)
                    updated_mapping[akahu_id].pop('actual_budget_id', None)
                    updated_mapping[akahu_id].pop('actual_budget_name', None)
                    updated_mapping[akahu_id].pop('actual_account_name', None)
                logging.info(f"Removed Actual account with ID {actual_id} from Akahu mapping {akahu_id}.")
            for ynab_id, akahu_id in ynab_to_delete:
                if updated_mapping[akahu_id].get('ynab_account_id') == ynab_id:
                    updated_mapping[akahu_id].pop('ynab_account_id', None)
                    updated_mapping[akahu_id].pop('ynab_budget_id', None)
                    updated_mapping[akahu_id].pop('ynab_budget_name', None)
                    updated_mapping[akahu_id].pop('ynab_account_name', None)
                logging.info(f"Removed YNAB account with ID {ynab_id} from Akahu mapping {akahu_id}.")

    # Return updated mappings
    return updated_mapping, combined_akahu_accounts, combined_actual_accounts, combined_ynab_accounts



# Fetch Akahu accounts using the Akahu API
def fetch_akahu_accounts():
    logging.info("Fetching Akahu accounts...")
    response = requests.get(f"{akahu_endpoint}/accounts", headers=akahu_headers)
    if response.status_code != 200:
        logging.error(f"Failed to fetch Akahu accounts: {response.status_code} {response.text}")
        raise RuntimeError(f"Failed to fetch Akahu accounts: {response.status_code}")

    accounts_data = response.json().get("items", [])
    akahu_accounts = {}
    for acc in accounts_data:
        if acc.get("status", "").upper() == "ACTIVE":
            acc_copy = acc.copy()

            # Rename '_id' to 'id' in the copied dictionary
            acc_copy = {
                'id' if key == '_id' else key: value
                for key, value in acc_copy.items()
            }
            # Transform 'connection' to keep only the 'name'
            if 'connection' in acc_copy and isinstance(acc_copy['connection'], dict):
                acc_copy['connection'] = acc_copy['connection'].get('name', "Unknown Connection")

            # Use the updated 'id' value as the key for akahu_accounts
            akahu_accounts[acc_copy['id']] = acc_copy

    logging.info(f"Fetched {len(akahu_accounts)} Akahu accounts.")
    return akahu_accounts


def validate_user_input(response_content, target_accounts, akahu_to_account_mapping, target_account_key):
    """
    Validates the user input from OpenAI response to ensure it's a valid selection.

    Parameters:
    - response_content: str
        The content of the response from OpenAI, which should be a number.
    - target_accounts: list of dicts
        The original list of target accounts, each represented as a dictionary.
    - akahu_to_account_mapping: dict
        The current mappings, which provides the details about what Akahu accounts are already mapped.
    - target_account_key: str
        The key representing the type of account to look for in the mapping (e.g., 'actual_account_id' or 'ynab_account_id').

    Returns:
    - int or None
        The validated 1-based index of the chosen target account, or None if invalid.
    """
    try:
        # Attempt to convert the response to an integer
        chosen_seq = int(response_content)

        # Handle the 'no match' case where chosen_seq is 0
        if chosen_seq == 0:
            return 0

        # Find the account with the matching sequence number
        account = next((account for account in target_accounts if account['seq'] == chosen_seq), None)
        if account is not None:
            account_id = account['id']

            # Ensure the chosen account is not marked as "Already Mapped"
            if not any(account_id == mapping.get(target_account_key) for mapping in akahu_to_account_mapping.values()):
                return chosen_seq
    except ValueError:
        # If response_content cannot be converted to an integer, it's invalid
        return None

    # If any checks fail, return None
    return None


def get_openai_match_suggestion(akahu_account, target_accounts, akahu_to_account_mapping, target_account_key):
    """
    Parameters:
    - akahu_account: dict
        A dictionary containing details about the Akahu account that needs a mapping.
        For example: {'id': 'akahu_id_123', 'name': 'Account Name', 'connection': 'Bank Name'}
    - target_accounts: list of dicts
        A list of target accounts, each represented as a dictionary with fields like 'id' and 'name'.
        For example: [{'id': 'target_id_1', 'name': 'Target Account 1'}, {'id': 'target_id_2', 'name': 'Target Account 2'}]
    - akahu_to_account_mapping: dict
        The current mappings, which provides the details about what Akahu accounts are already mapped.
        For example: {'akahu_id_123': {'actual_account_id': 'target_id_2'}}
    - target_account_key: str
        The key representing the type of account to look for in the mapping (e.g., 'actual_account_id' or 'ynab_account_id').

    Returns:
    - int or None
        A valid numeric index of the suggested target account (1-based index as presented to the user)
        or None if no suggestion can be confidently made.
    """

    # Generate the prompt preamble
    prompt = (
        "You are an expert in financial account mapping. Your task is to match the given Akahu account with one of the provided target accounts. "
        "Please provide the number corresponding to the best match. Even if you are not completely certain, make the best choice you can based on the information provided.\n\n"

        "Akahu Account:\n"
        f"Name: {akahu_account['name']}\n"
        f"Connection: {akahu_account['connection']}\n\n"
        "Here is a list of target accounts:\n"
    )
    prompt += f"0. This account probably does not match any options\n"

    # Add each target account to the prompt, skipping already mapped accounts
    for idx, account in enumerate(target_accounts, start=1):
        account_id = account['id']
        account_name = account['name']
        account_seq = account['seq']

        # Skip already mapped target accounts based on the existing mapping
        if any(account_id == mapping.get(target_account_key) for mapping in akahu_to_account_mapping.values()):
            continue  # Skip this account

        # Add the current valid target account to the prompt
        prompt += f"{account_seq}. {account_name}\n"


    # Add the instruction at the end of the prompt
    prompt += "\nPlease type the number corresponding to the best match:"

    try:
        # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": "Select the best match by responding with a number, including 0 if no match is suitable. Respond strictly with a number—no explanations or commentary. Any other output will be treated as invalid."},
                 {"role": "user", "content": prompt}
            ],
            max_tokens=2,
            temperature=0,
        )

        # Extract and validate the response
        response_content = response.choices[0].message.content.strip()
        chosen_index = validate_user_input(response_content, target_accounts, akahu_to_account_mapping, target_account_key)
        if chosen_index is not None:
            return chosen_index
    except Exception as e:
        # Log the exception (could be network error, API rate limit, etc.)
        logging.error(f"OpenAI API call failed or gave an invalid response: {str(e)}")

    # Fallback to FuzzyWuzzy if OpenAI fails or gives an invalid response
    return get_fuzzy_match_suggestion(akahu_account, target_accounts, akahu_to_account_mapping, target_account_key)

def get_fuzzy_match_suggestion(akahu_account, target_accounts, akahu_to_account_mapping, target_account_key):
    """
    Parameters:
    - akahu_account: dict
        A dictionary containing details about the Akahu account that needs a mapping.
        For example: {'id': 'akahu_id_123', 'name': 'Account Name', 'connection': 'Bank Name'}
    - target_accounts: list of dicts
        A list of target accounts, each represented as a dictionary with fields like 'id' and 'name'.
        For example: [{'id': 'target_id_1', 'name': 'Target Account 1'}, {'id': 'target_id_2', 'name': 'Target Account 2'}]
    - akahu_to_account_mapping: dict
        The current mappings, which provide the details about what Akahu accounts are already mapped.
        For example: {'akahu_id_123': {'actual_account_id': 'target_id_2'}}
    - target_account_key: str
        The key representing the type of account to look for in the mapping (e.g., 'actual_account_id' or 'ynab_account_id').

    Returns:
    - int or None
        A valid numeric index of the suggested target account (1-based index as presented to the user)
        or None if no suggestion can be confidently made.
    """
    # Create a list of unmapped target account names and their corresponding original indices for fuzzy matching
    unmapped_accounts = []
    unmapped_indices = []
    logging.info("Falling back to FuzzyWuzzy for matching suggestion.")
    for idx, target_account in enumerate(target_accounts, start=1):
        account_id = target_account['id']
        account_name = target_account['name']
        account_seq = target_account['seq']

        # Skip already mapped target accounts based on the existing mapping
        if any(account_id == mapping.get(target_account_key) for mapping in akahu_to_account_mapping.values()):
            continue  # Skip this account

        # Add the current valid target account to the list for fuzzy matching
        unmapped_accounts.append(account_name)
        unmapped_indices.append(idx)  # Keep track of the original index (1-based)

    # Perform fuzzy matching on the Akahu account name against the unmapped target accounts
    if unmapped_accounts:
        best_match_name, confidence = process.extractOne(akahu_account['name'], unmapped_accounts)
        if confidence >= 50:  # Use a confidence threshold to determine if the match is reliable
            # Find the corresponding index for the best match
            best_match_index = unmapped_accounts.index(best_match_name)
            original_index = unmapped_indices[best_match_index]
            return original_index  # Return the original 1-based index

    # Return None if no confident match is found
    return "0"


def seq_to_acct(suggested_index, target_accounts):
    return next((acct for acct in target_accounts if acct['seq'] == suggested_index), None)


def match_accounts(akahu_to_account_mapping, akahu_accounts, target_accounts, account_type, use_openai=True):
    """
    Updated to handle accounts as dictionaries instead of lists.
    """
    if account_type == 'actual':
        target_account_key = 'actual_account_id'
        target_account_name = 'actual_account_name'
    elif account_type == 'ynab':
        target_account_key = 'ynab_account_id'
        target_account_name = 'ynab_account_name'
    else:
        raise ValueError("Invalid account type provided. Must be either 'actual' or 'ynab'.")

    # Convert target_accounts to list and add sequence numbers
    target_accounts_list = sorted(target_accounts.values(), key=lambda x: x['name'].lower())
    for idx, target_account in enumerate(target_accounts_list, start=1):
        target_account['seq'] = idx

    for akahu_id, akahu_account in sorted(akahu_accounts.items(), key=lambda x: x[1]['name'].lower()):
        akahu_name = akahu_account['name']

        # Check if Akahu account is already mapped
        if akahu_id in akahu_to_account_mapping and target_account_key in akahu_to_account_mapping[akahu_id]:
            print(f"Akahu account '{akahu_name}' is already mapped to {account_type.capitalize()} account. Skipping.")
            continue

        # Get suggestion using either OpenAI or FuzzyWuzzy
        if use_openai:
            suggested_index = get_openai_match_suggestion(akahu_account, target_accounts_list, akahu_to_account_mapping,
                                                          target_account_key)
        else:
            suggested_index = get_fuzzy_match_suggestion(akahu_account, target_accounts_list, akahu_to_account_mapping,
                                                         target_account_key)

        # Display the Akahu account details
        print(f"\nAkahu Account: {akahu_name} (Connection: {akahu_account['connection']})")
        print(f"Here is a list of {account_type} accounts:")

        for target_account in target_accounts_list:
            account_id = target_account['id']
            account_name = target_account['name']
            seq = target_account['seq']

            # Display accounts, including if they are already mapped
            if any(account_id == mapping.get(target_account_key) for mapping in akahu_to_account_mapping.values()):
                print(f"{seq}. {account_name} (Already Mapped)")
            else:
                print(f"{seq}. {account_name}")

        # Display the suggestion if one exists
        if suggested_index == 0:
            print("No suitable match found.")
        elif suggested_index is not None:
            print(f"Suggested match: {suggested_index}. {seq_to_acct(suggested_index, target_accounts_list)['name']}")
        else:
            logging.debug("No confident match found.")

        # Prompt user for input
        user_input = input("Enter the number corresponding to the best match (or press Enter to skip): ")
        validated_index = validate_user_input(user_input, target_accounts_list, akahu_to_account_mapping,
                                              target_account_key)
        if validated_index is None:
            if user_input != "":
                print("Invalid input.")
            continue
        else:
            selected_account = seq_to_acct(validated_index, target_accounts_list)
            selected_id = selected_account['id']
            selected_name = selected_account['name']
            akahu_to_account_mapping.setdefault(akahu_id, {}).update({
                target_account_key: selected_id,
                target_account_name: selected_name,
                "akahu_id": akahu_id,
                "akahu_name": akahu_name,
                f"{account_type}_matched_date": datetime.now().isoformat(),
            })
            print(f"Mapped Akahu account '{akahu_name}' to target account '{selected_name}'.")

    return akahu_to_account_mapping


def remove_seq(data):
    """
    Recursively removes 'seq' keys from dictionaries while preserving structure.
    Works with nested dictionaries and dictionary values in lists.

    Args:
        data: Can be a dictionary, list, or any other type

    Returns:
        The same data structure with all 'seq' keys removed from any dictionaries
    """
    if isinstance(data, dict):
        return {
            key: remove_seq(value)
            for key, value in data.items()
            if key != 'seq'
        }
    elif isinstance(data, list):
        return [remove_seq(item) for item in data]
    else:
        return data


def save_mapping(data_to_save, mapping_file="akahu_budget_mapping.json"):
    """
    Saves the mapping along with Akahu, Actual, and YNAB accounts to a JSON file.


    :param data_to_save: dictionary comprising
     mapping: The current mapping of Akahu to Actual and/or YNAB accounts.
     akahu_accounts: Dictionary of Akahu accounts.
     actual_accounts: Dictionary of Actual accounts.
     ynab_accounts: Dictionary of YNAB accounts.
    :param mapping_file: The file path to save the mapping JSON.
    """
    # Construct final data dictionary

    # Save the new mapping dictionary to JSON
    try:
        # Attempt to serialize the data to JSON in memory
        serialized_data = json.dumps(data_to_save, indent=4)
        data_dict = json.loads(serialized_data)
        required_keys = {"akahu_accounts", "actual_accounts", "ynab_accounts", "mapping"}

        # Check if all required keys are present
        if not required_keys.issubset(data_dict.keys()):
            raise ValueError(
                f"Serialized data is missing one or more required keys: {required_keys - data_dict.keys()}")

        # Only open the file for writing if serialization is successful
        with open(mapping_file, "w") as f:
            f.write(serialized_data)

        logging.info("New mapping saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save mapping: {e}")


def check_for_changes(existing_akahu_accounts, latest_akahu_accounts, existing_actual_accounts, latest_actual_accounts, existing_ynab_accounts, latest_ynab_accounts):
    akahu_accounts_match = True

    for key in existing_akahu_accounts:
        if key in latest_akahu_accounts:
            if not shallow_compare_dicts(existing_akahu_accounts[key], latest_akahu_accounts[key]):
                akahu_accounts_match = False
                break
        else:
            akahu_accounts_match = False
            break

    # Compare existing_actual_accounts and latest_actual_accounts
    actual_accounts_match = True

    for key in existing_actual_accounts:
        if key in latest_actual_accounts:
            if not shallow_compare_dicts(existing_actual_accounts[key], latest_actual_accounts[key]):
                actual_accounts_match = False
                break
        else:
            actual_accounts_match = False
            break

    # Compare existing_ynab_accounts and latest_ynab_accounts
    ynab_accounts_match = True

    for key in existing_ynab_accounts:
        if key in latest_ynab_accounts:
            if not shallow_compare_dicts(existing_ynab_accounts[key], latest_ynab_accounts[key]):
                ynab_accounts_match = False
                break
        else:
            ynab_accounts_match = False
            break
    return (akahu_accounts_match, actual_accounts_match, ynab_accounts_match)

# Initialize and use the Actual class directly
def main():
    logging.info("Starting Akahu API integration script.")

    try:
        latest_actual_accounts = {}
        latest_ynab_accounts = {}

        if SYNC_TO_AB:
            with Actual(
                base_url=ENVs['ACTUAL_SERVER_URL'],
                password=ENVs['ACTUAL_PASSWORD'],
                file=ENVs['ACTUAL_SYNC_ID'],
                encryption_password=ENVs['ACTUAL_ENCRYPTION_KEY']
            ) as actual:
                logging.info("Actual Budget API initialized successfully.")
                latest_actual_accounts = fetch_actual_accounts(actual)
                logging.info(f"Fetched {len(latest_actual_accounts)} Actual Budget accounts.")

        else:
            logging.info("Not syncing to Actual Budget")

        if SYNC_TO_YNAB:
            latest_ynab_accounts = fetch_ynab_accounts()
            logging.info(f"Fetched {len(latest_ynab_accounts)} YNAB accounts.")
        else:
            logging.info("Not syncing to YNAB")

        # Step 0: Load existing mapping and validate
        existing_akahu_accounts, existing_actual_accounts, existing_ynab_accounts, existing_mapping = load_existing_mapping()

        # Step 1: Fetch Akahu accounts (now returns dictionary)
        latest_akahu_accounts = fetch_akahu_accounts()

        # Step 4: Validate and update existing mapping
        existing_mapping, akahu_accounts, actual_accounts, ynab_accounts = merge_and_update_mapping(
            existing_mapping,
            latest_akahu_accounts,
            latest_actual_accounts,
            latest_ynab_accounts,
            existing_akahu_accounts,
            existing_actual_accounts,
            existing_ynab_accounts
        )

        akahu_accounts = dict(sorted(
            akahu_accounts.items(),
            key=lambda x: x[1]['name'].lower()
        ))

        new_mapping = existing_mapping.copy()

        # Compare existing_akahu_accounts and latest_akahu_accounts
        (akahu_accounts_match, actual_accounts_match, ynab_accounts_match) = check_for_changes(existing_akahu_accounts, latest_akahu_accounts, existing_actual_accounts, latest_actual_accounts, existing_ynab_accounts, latest_ynab_accounts)
        # Check if all comparisons match, then exit if true
        if akahu_accounts_match and actual_accounts_match and ynab_accounts_match:
            logging.info("No changes detected in Akahu, Actual, or YNAB accounts. Skipping match")
        else:
            # Step 6: Match Akahu accounts to YNAB accounts interactively
            if SYNC_TO_YNAB:
                new_mapping = match_accounts(new_mapping, akahu_accounts, ynab_accounts, "ynab", use_openai=True)

            # Step 5: Match Akahu accounts to Actual accounts interactively
            if SYNC_TO_AB:
                new_mapping = match_accounts(new_mapping, akahu_accounts, actual_accounts, "actual", use_openai=True)

        # Step 7: Output proposed mapping and save
        data_to_save = {
            "akahu_accounts": akahu_accounts,
            "actual_accounts": actual_accounts,
            "ynab_accounts": ynab_accounts,
            "mapping": new_mapping
        }

        data_without_seq = remove_seq(data_to_save)
        save_mapping(data_without_seq)

    except Exception as e:
        logging.exception("An unexpected error occurred during script execution.")


if __name__ == "__main__":
    main()
