"""Persistence helpers for the Akahu budget mapping file."""

import json
import logging


def generate_mapping_stub(mapping_file="akahu_budget_mapping.json"):
    """Generate a stub JSON file for the mapping."""
    stub = {
        "akahu_accounts": {},
        "actual_accounts": {},
        "ynab_accounts": {},
        "mapping": {},
    }
    with open(mapping_file, "w") as f:
        json.dump(stub, f, indent=4)
    print(f"Stub mapping file created: {mapping_file}")


def load_existing_mapping(mapping_file="akahu_budget_mapping.json", generate_stub=False):
    """Load existing mapping from JSON file."""
    try:
        with open(mapping_file, "r") as f:
            data = json.load(f)
            required_fields = [
                "akahu_accounts",
                "actual_accounts",
                "ynab_accounts",
                "mapping",
            ]
            if not all(field in data for field in required_fields):
                raise ValueError(
                    f"Mapping file missing required fields: {required_fields}"
                )

            mapping = data.get("mapping", {})
            if isinstance(mapping, list):
                mapping = {
                    entry["akahu_id"]: entry for entry in mapping if "akahu_id" in entry
                }
            return (
                data["akahu_accounts"],
                data["actual_accounts"],
                data["ynab_accounts"],
                mapping,
            )
    except FileNotFoundError:
        logging.warning("Mapping file not found - first run ever?")
        generate_mapping_stub(mapping_file=mapping_file)
        return load_existing_mapping(mapping_file=mapping_file, generate_stub=False)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in mapping file {mapping_file}")


def remove_seq(data):
    """Recursively removes 'seq' keys from dictionaries while preserving structure."""
    if isinstance(data, dict):
        return {key: remove_seq(value) for key, value in data.items() if key != "seq"}
    if isinstance(data, list):
        return [remove_seq(item) for item in data]
    return data


def save_mapping(data_to_save, mapping_file="akahu_budget_mapping.json"):
    """Saves the mapping along with Akahu, Actual, and YNAB accounts to a JSON file."""
    try:
        serialized_data = json.dumps(data_to_save, indent=4)
        data_dict = json.loads(serialized_data)
        required_keys = {
            "akahu_accounts",
            "actual_accounts",
            "ynab_accounts",
            "mapping",
        }

        if not required_keys.issubset(data_dict.keys()):
            raise ValueError(
                f"Serialized data is missing one or more required keys: {required_keys - data_dict.keys()}"
            )

        with open(mapping_file, "w") as f:
            f.write(serialized_data)
    except Exception as e:
        logging.error(f"Failed to save mapping: {e}")
        raise
