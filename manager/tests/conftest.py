import os
import sys
import pytest
import json

# Add manager directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def mock_registry_file(tmp_path):
    """Creates a mock app registry file for testing."""
    registry_dir = tmp_path / "registry-log"
    registry_dir.mkdir()
    registry_file = registry_dir / "app_import_registry.json"
    
    dummy_data = {
        "eval": [
            {"name": "App1", "developerEmail": "dev1@example.com"},
            {"name": "App2", "developerEmail": "dev2@example.com"}
        ]
    }
    
    with open(registry_file, 'w') as f:
        json.dump(dummy_data, f)
        
    return str(registry_file)
