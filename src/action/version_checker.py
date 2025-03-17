import requests
from bs4 import BeautifulSoup
import sys
import yaml
import pathlib
import json
import os
import re
import time
from typing import Optional, Tuple, Dict, List, Any
from enum import Enum

class SolanaNetwork(Enum):
    MAINNET = "mainnet-beta"
    TESTNET = "testnet"
    DEVNET = "devnet"

    @classmethod
    def from_str(cls, value: str) -> 'SolanaNetwork':
        value = value.lower()
        if value == "mainnet" or value == "mainnet-beta":
            return cls.MAINNET
        elif value == "testnet":
            return cls.TESTNET
        elif value == "devnet":
            return cls.DEVNET
        else:
            raise ValueError(f"Invalid network: {value}. Must be one of: mainnet, testnet, devnet")

    def get_rpc_url(self) -> str:
        """Return the default RPC URL for this network."""
        if self == SolanaNetwork.MAINNET:
            return "https://api.mainnet-beta.solana.com"
        elif self == SolanaNetwork.TESTNET:
            return "https://api.testnet.solana.com"
        elif self == SolanaNetwork.DEVNET:
            return "https://api.devnet.solana.com"
        else:
            raise ValueError(f"Unknown network: {self}")

class VersionInfo:
    def __init__(self, epoch: int, agave_min: str, agave_max: str = None,
                 firedancer_min: str = None, firedancer_max: str = None):
        self.epoch = epoch
        self.agave_min = agave_min
        self.agave_max = agave_max if agave_max and agave_max != "-" else None
        self.firedancer_min = firedancer_min
        self.firedancer_max = firedancer_max if firedancer_max and firedancer_max != "-" else None

def get_current_epoch(network: SolanaNetwork, custom_rpc_url: Optional[str] = None,
                     max_retries: int = 3, retry_delay: int = 2) -> Optional[int]:
    """
    Get the current epoch from the Solana RPC endpoint with retry mechanism.

    Args:
        network: The Solana network to query
        custom_rpc_url: Optional custom RPC URL to use instead of default
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Returns:
        Current epoch as an integer, or None if the request fails
    """
    rpc_url = custom_rpc_url or network.get_rpc_url()

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getEpochInfo",
        "params": []
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(rpc_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()

            data = response.json()
            if "result" in data and "epoch" in data["result"]:
                return int(data["result"]["epoch"])
            else:
                print(f"Warning: Unexpected RPC response format: {data}")

        except requests.exceptions.RequestException as e:
            print(f"RPC request failed (attempt {attempt+1}/{max_retries}): {e}")

        except (ValueError, KeyError, TypeError) as e:
            print(f"Error parsing RPC response (attempt {attempt+1}/{max_retries}): {e}")

        # Don't sleep after the last attempt
        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    print(f"Failed to get current epoch after {max_retries} attempts")
    return None

class VersionChecker:
    def __init__(self, yaml_path: str, network: str = "testnet", current_epoch: Optional[int] = None,
                 custom_rpc_url: Optional[str] = None, delegation_criteria_url: str = 'https://solana.org/delegation-criteria'):
        self.yaml_path = pathlib.Path(yaml_path)
        self.network = SolanaNetwork.from_str(network)
        self.custom_rpc_url = custom_rpc_url
        self.delegation_criteria_url = delegation_criteria_url
        self.version_table = []

        # If current_epoch is not provided, try to fetch it from RPC
        if current_epoch is None:
            self.current_epoch = get_current_epoch(self.network, self.custom_rpc_url)
            if self.current_epoch is not None:
                print(f"Successfully retrieved current epoch from RPC: {self.current_epoch}")
            else:
                print("Warning: Could not retrieve current epoch from RPC")
                self.current_epoch = None
        else:
            self.current_epoch = current_epoch

    def parse_version_table(self, html_content: str) -> List[VersionInfo]:
        """Parse the HTML table containing version requirements."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Find tables that might contain version information
            tables = soup.find_all('table')
            version_table = []

            for table in tables:
                # Check if this table has the expected headers
                headers = [th.get_text().strip() for th in table.find_all('th')]
                if 'Epoch' in headers and 'Agave Min.' in headers:
                    # This looks like our version table
                    for row in table.find_all('tr')[1:]:  # Skip header row
                        cells = row.find_all('td')
                        if len(cells) >= 5:  # Ensure we have enough cells
                            try:
                                epoch = int(cells[0].get_text().strip())
                                agave_min = cells[1].get_text().strip()
                                agave_max = cells[2].get_text().strip()
                                firedancer_min = cells[3].get_text().strip()
                                firedancer_max = cells[4].get_text().strip()

                                version_table.append(VersionInfo(
                                    epoch=epoch,
                                    agave_min=agave_min,
                                    agave_max=agave_max,
                                    firedancer_min=firedancer_min,
                                    firedancer_max=firedancer_max
                                ))
                            except (ValueError, IndexError) as e:
                                print(f"Error parsing row: {e}")
                                continue

            # Sort by epoch to ensure we have them in order
            version_table.sort(key=lambda x: x.epoch)
            return version_table

        except Exception as e:
            print(f"Error parsing version table: {e}")
            return []

    def get_required_version(self) -> Optional[str]:
        """Get the required Agave version based on the current epoch."""
        try:
            headers = {
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
                "cache-control": "no-cache"
            }
            response = requests.get(self.delegation_criteria_url, headers=headers)
            response.raise_for_status()

            # Parse the version table
            self.version_table = self.parse_version_table(response.text)

            if not self.version_table:
                print("Warning: Could not find version table in the delegation criteria page")
                return None

            # If we have a current epoch, find the appropriate version
            if self.current_epoch:
                applicable_version = None
                for version_info in reversed(self.version_table):
                    if self.current_epoch >= version_info.epoch:
                        return version_info.agave_min

                print(f"Warning: No version requirement found for epoch {self.current_epoch}")
                return None
            else:
                # If no epoch is available, use the latest version requirement
                latest_version_info = max(self.version_table, key=lambda x: x.epoch)
                return latest_version_info.agave_min

        except Exception as e:
            print(f"Error fetching version: {e}", file=sys.stderr)
            return None

    def get_current_version(self) -> str:
        """Get the current Solana version from the YAML file."""
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Could not find YAML file at {self.yaml_path}")

        try:
            with open(self.yaml_path) as f:
                # Load all documents and merge them
                documents = list(yaml.safe_load_all(f))
                merged_data = {}
                for doc in documents:
                    if doc:  # Skip empty documents
                        merged_data.update(doc)

                if not merged_data:
                    raise ValueError("No valid YAML content found")

                return merged_data['spec']['values']['image']['tag']
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML file: {e}")
        except KeyError as e:
            raise ValueError(f"Required key not found in YAML: {e}")

    def update_yaml_version(self, new_version: str) -> None:
        """Update the Solana version in the YAML file while preserving formatting and multiple documents."""
        try:
            with open(self.yaml_path, 'r') as f:
                content = f.read()

            # Get the current version
            current_version = self.get_current_version()

            # Create all possible patterns for the version tag
            patterns = [
                f'tag: {current_version}',      # No quotes
                f'tag: "{current_version}"',    # Double quotes
                f"tag: '{current_version}'"     # Single quotes
            ]

            updated_content = content
            for pattern in patterns:
                if pattern in content:
                    # Determine which quote style was used
                    if '"' in pattern:
                        updated_content = content.replace(pattern, f'tag: "v{new_version}"')
                    elif "'" in pattern:
                        updated_content = content.replace(pattern, f"tag: 'v{new_version}'")
                    else:
                        updated_content = content.replace(pattern, f'tag: v{new_version}')
                    break

            # Verify the updated content is valid YAML before writing
            try:
                # Verify all documents in the YAML are still valid
                list(yaml.safe_load_all(updated_content))
            except yaml.YAMLError as e:
                raise ValueError(f"Generated invalid YAML: {e}")

            with open(self.yaml_path, 'w') as f:
                f.write(updated_content)
        except Exception as e:
            raise ValueError(f"Error updating YAML file: {e}")

    def check_and_update(self) -> Tuple[str, str, bool]:
        """Check if an update is needed and perform it if necessary."""
        required_version = self.get_required_version()
        if not required_version:
            raise ValueError("Could not find required version information")

        current_version = self.get_current_version().replace('v', '')
        if current_version != required_version:
            self.update_yaml_version(required_version)
            return required_version, current_version, True

        return required_version, current_version, False

    def get_version_table_info(self) -> List[Dict]:
        """Return the version table information in a structured format."""
        return [
            {
                "epoch": info.epoch,
                "agave_min": info.agave_min,
                "agave_max": info.agave_max,
                "firedancer_min": info.firedancer_min,
                "firedancer_max": info.firedancer_max
            }
            for info in self.version_table
        ]

def main():
    try:
        network = os.environ.get('INPUT_NETWORK', 'testnet')
        custom_rpc_url = os.environ.get('INPUT_RPC_URL')
        delegation_criteria_url = os.environ.get('INPUT_DELEGATION_CRITERIA_URL', 'https://solana.org/delegation-criteria')

        # Check if epoch is explicitly provided
        provided_epoch = os.environ.get('INPUT_CURRENT_EPOCH')
        current_epoch = None

        if provided_epoch:
            try:
                current_epoch = int(provided_epoch)
                print(f"Using provided epoch: {current_epoch}")
            except ValueError:
                print(f"Warning: Invalid epoch value '{provided_epoch}', will attempt to fetch from RPC", file=sys.stderr)

        checker = VersionChecker(
            yaml_path=os.environ['INPUT_YAML_PATH'],
            network=network,
            current_epoch=current_epoch,
            custom_rpc_url=custom_rpc_url,
            delegation_criteria_url=delegation_criteria_url
        )

        required_version, current_version, changed = checker.check_and_update()

        print(f"Network: {network}")
        print(f"Current version: {current_version}")
        print(f"Required version: {required_version}")

        # Print version table information if available
        version_table = checker.get_version_table_info()
        if version_table:
            print("\nVersion requirements by epoch:")
            for info in version_table:
                print(f"Epoch {info['epoch']}: Agave {info['agave_min']} to {info['agave_max'] or 'latest'}, "
                      f"Firedancer {info['firedancer_min']} to {info['firedancer_max'] or 'latest'}")

            if checker.current_epoch:
                print(f"\nCurrent epoch: {checker.current_epoch}")
                # Find the applicable version requirement
                applicable_version = None
                for info in reversed(version_table):
                    if checker.current_epoch >= info['epoch']:
                        applicable_version = info
                        break

                if applicable_version:
                    print(f"Applicable version requirement: Agave {applicable_version['agave_min']}")

        if changed:
            print(f"::set-output name=min-version::{required_version}")
            print(f"::set-output name=current-version::{current_version}")
            print("::set-output name=should-update::true")
            if checker.current_epoch:
                print(f"::set-output name=current-epoch::{checker.current_epoch}")
        else:
            print("::set-output name=should-update::false")
            if checker.current_epoch:
                print(f"::set-output name=current-epoch::{checker.current_epoch}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
