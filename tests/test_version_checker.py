import pytest
from action.version_checker import VersionChecker, SolanaNetwork
import yaml

@pytest.fixture
def sample_yaml(tmp_path):
    yaml_content = {
        'spec': {
         'values': {
            'image': {
                'repository': 'anzaxyz/agave',
                'pullPolicy': 'IfNotPresent',
                'tag': 'v2.1.13'
            }
         }
       }
    }
    yaml_path = tmp_path / "test.yml"
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_content, f)
    return yaml_path

def test_get_current_version(sample_yaml):
    checker = VersionChecker(str(sample_yaml))
    assert checker.get_current_version() == 'v2.1.13'

def test_update_yaml_version(sample_yaml):
    checker = VersionChecker(str(sample_yaml))
    new_version = '2.1.14'
    checker.update_yaml_version(new_version)
    assert checker.get_current_version().replace("v", "") == new_version

def test_invalid_network():
    with pytest.raises(ValueError, match="Invalid network"):
        VersionChecker("test.yml", network="invalid")

@pytest.mark.parametrize("network_input,expected", [
    ("mainnet", SolanaNetwork.MAINNET),
    ("mainnet-beta", SolanaNetwork.MAINNET),
    ("testnet", SolanaNetwork.TESTNET),
    ("devnet", SolanaNetwork.DEVNET),
])
def test_network_parsing(network_input, expected):
    checker = VersionChecker("test.yml", network=network_input)
    assert checker.network == expected