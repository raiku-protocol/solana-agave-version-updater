import requests
from bs4 import BeautifulSoup
import sys
import yaml
import pathlib
import json
import os
from typing import Optional, Tuple
from enum import Enum

url = 'https://solana.org/delegation-criteria'

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

class VersionChecker:
    def __init__(self, yaml_path: str, network: str = "testnet"):
        self.yaml_path = pathlib.Path(yaml_path)
        self.network = SolanaNetwork.from_str(network)

    def extract_version_from_html(self, html_content: str) -> Optional[str]:
        """Extract version from embedded JSON data in the page."""
        import json
        import re

        try:
            # First find the script tag containing __NEXT_DATA__
            script_pattern = r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'
            script_match = re.search(script_pattern, html_content, re.DOTALL)

            if not script_match:
                print("Could not find __NEXT_DATA__ script tag")
                print("HTML content preview:", html_content[:200])  # Debug preview
                return None

            # Extract and parse the JSON data
            json_str = script_match.group(1)
            json_data = json.loads(json_str)

            # Determine the correct data path based on the network
            if self.network == SolanaNetwork.MAINNET:
                network_data = json_data['props']['pageProps']['mbData']
            else:
                network_data = json_data['props']['pageProps']['tnData']

            # Get version from baseline criteria
            baseline_criteria = network_data['baselineCriteria']
            versions = []
            for criterion in baseline_criteria:
                if criterion['metric'] == 'Solana release':
                    version = criterion['needed'].replace('≥ ', '').strip()
                    versions.append(version)

            if not versions:
                return None

            return versions[0]

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON data: {e}")
            print("JSON content preview:", json_str[:200] if 'json_str' in locals() else "No JSON found")
            return None
        except KeyError as e:
            print(f"Failed to find expected key in JSON structure: {e}")
            if 'json_data' in locals():
                print("Available keys:", json_data.keys() if hasattr(json_data, 'keys') else "No keys")
            return None
        except Exception as e:
            print(f"Unexpected error parsing version data: {e}")
            return None

    def get_required_version(self) -> Optional[str]:
        """Get the required Solana version from the network's baseline requirements."""
        try:
            headers = {
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
                "cache-control": "no-cache"
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            version = self.extract_version_from_html(response.text)
            if not version:
                print(f"Warning: Could not find version information for {self.network.value}", file=sys.stderr)
                return None

            return version

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

def main():
    try:
        network = os.environ.get('INPUT_NETWORK', 'testnet')
        checker = VersionChecker(
            yaml_path=os.environ['INPUT_YAML_PATH'],
            network=network
        )

        required_version, current_version, changed = checker.check_and_update()

        print(f"Network: {network}")
        print(f"Current version: {current_version}")
        print(f"Required version: {required_version}")

        if changed:
            print(f"::set-output name=min-version::{required_version}")
            print(f"::set-output name=current-version::{current_version}")
            print("::set-output name=should-update::true")
        else:
            print("::set-output name=should-update::false")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()