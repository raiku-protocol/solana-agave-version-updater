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

@pytest.fixture
def multi_doc_yaml(tmp_path):
    doc1 = {
        'apiVersion': 'v1',
        'kind': 'ConfigMap',
        'metadata': {'name': 'config1'}
    }
    doc2 = {
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
    yaml_path = tmp_path / "multi_doc.yml"
    with open(yaml_path, 'w') as f:
        yaml.dump_all([doc1, doc2], f)
    return yaml_path

def test_get_current_version(sample_yaml):
    checker = VersionChecker(str(sample_yaml))
    assert checker.get_current_version() == 'v2.1.13'

def test_get_current_version_multi_doc(multi_doc_yaml):
    checker = VersionChecker(str(multi_doc_yaml))
    assert checker.get_current_version() == 'v2.1.13'

def test_update_yaml_version(sample_yaml):
    checker = VersionChecker(str(sample_yaml))
    new_version = '2.1.14'
    checker.update_yaml_version(new_version)
    assert checker.get_current_version().replace("v", "") == new_version

def test_update_yaml_version_multi_doc(multi_doc_yaml):
    checker = VersionChecker(str(multi_doc_yaml))
    new_version = '2.1.14'
    checker.update_yaml_version(new_version)

    # Verify the version was updated
    assert checker.get_current_version().replace("v", "") == new_version

    # Verify both documents are preserved
    with open(multi_doc_yaml) as f:
        docs = list(yaml.safe_load_all(f))
        assert len(docs) == 2
        assert docs[0]['apiVersion'] == 'v1'
        assert docs[0]['kind'] == 'ConfigMap'
        assert docs[1]['spec']['values']['image']['tag'] == f'v{new_version}'

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

def test_missing_yaml_file():
    checker = VersionChecker("nonexistent.yml")
    with pytest.raises(FileNotFoundError):
        checker.get_current_version()

def test_malformed_yaml(tmp_path):
    yaml_path = tmp_path / "malformed.yml"
    with open(yaml_path, 'w') as f:
        f.write("}{invalid:yaml")

    checker = VersionChecker(str(yaml_path))
    with pytest.raises(ValueError, match="Error parsing YAML file"):
        checker.get_current_version()

def test_missing_version_key(tmp_path):
    yaml_path = tmp_path / "missing_key.yml"
    with open(yaml_path, 'w') as f:
        yaml.dump({'spec': {'values': {'image': {}}}}, f)

    checker = VersionChecker(str(yaml_path))
    with pytest.raises(ValueError, match="Required key not found"):
        checker.get_current_version()