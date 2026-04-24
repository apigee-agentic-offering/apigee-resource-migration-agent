import os
import json
import unittest
import tempfile
import shutil
import sys
import types
from tools import config_tools

class TestConfigTools(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = os.path.join(self.test_dir, "registry-log")
        os.makedirs(self.registry_dir)
        self.registry_file = os.path.join(self.registry_dir, "app_import_registry.json")
        
        # Create a mock config module
        self.mock_config = types.ModuleType('config')
        self.mock_config.REGISTRY_LOG_DIR = "registry-log"
        self.mock_config.APP_REGISTRY_FILE = "app_import_registry.json"
        
        # Save original if exists
        self.original_config = sys.modules.get('config')
        sys.modules['config'] = self.mock_config
        
        self.original_root = config_tools.PROJECT_ROOT
        config_tools.PROJECT_ROOT = self.test_dir

    def tearDown(self):
        config_tools.PROJECT_ROOT = self.original_root
        if self.original_config:
            sys.modules['config'] = self.original_config
        else:
            del sys.modules['config']
        shutil.rmtree(self.test_dir)

    def test_check_app_registry_exists(self):
        dummy_data = {
            "eval": [
                {"name": "App1", "developerEmail": "dev1@example.com"}
            ]
        }
        with open(self.registry_file, 'w') as f:
            json.dump(dummy_data, f)
            
        result = config_tools.check_app_registry("eval")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["found"])
        self.assertIn("Found valid App records", result["message"])

    def test_check_app_registry_not_exists(self):
        dummy_data = {
            "eval": []
        }
        with open(self.registry_file, 'w') as f:
            json.dump(dummy_data, f)
            
        result = config_tools.check_app_registry("eval")
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["found"])
        self.assertIn("No Apps found", result["message"])

    def test_check_app_registry_org_missing(self):
        dummy_data = {
            "other_org": []
        }
        with open(self.registry_file, 'w') as f:
            json.dump(dummy_data, f)
            
        result = config_tools.check_app_registry("eval")
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["found"])

    def test_check_app_registry_file_missing(self):
        result = config_tools.check_app_registry("eval")
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["found"])
        self.assertIn("Registry file does not exist", result["message"])

    def test_check_app_registry_corrupt_json(self):
        with open(self.registry_file, 'w') as f:
            f.write("invalid json")
            
        result = config_tools.check_app_registry("eval")
        self.assertEqual(result["status"], "error")
        self.assertIn("corrupt", result["message"])

    def test_update_config_source_dir(self):
        config_path = os.path.join(self.test_dir, "config.py")
        with open(config_path, 'w') as f:
            f.write('SOURCE_DIR = "old_dir"\n')
            
        # We need to mock CONFIG_PATH in config_tools because it's computed at module level!
        # In config_tools.py: CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.py")
        # Since we mock PROJECT_ROOT in setUp, and CONFIG_PATH is computed using it?
        # Let's check config_tools.py lines 8-9:
        # PROJECT_ROOT = ...
        # CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.py")
        # Wait, CONFIG_PATH is computed ONCE when the module is loaded!
        # So mocking PROJECT_ROOT in setUp does NOT update CONFIG_PATH!
        # I need to mock CONFIG_PATH directly in the test!
        
        original_config_path = config_tools.CONFIG_PATH
        config_tools.CONFIG_PATH = config_path
        try:
            result = config_tools.update_config_source_dir("new_dir")
            self.assertEqual(result["status"], "success")
            
            with open(config_path, 'r') as f:
                content = f.read()
            self.assertIn('SOURCE_DIR = "new_dir"', content)
        finally:
            config_tools.CONFIG_PATH = original_config_path

    def test_update_config_sa_enable(self):
        config_path = os.path.join(self.test_dir, "config.py")
        with open(config_path, 'w') as f:
            f.write('SA_ENABLE = "false"\n')
            
        original_config_path = config_tools.CONFIG_PATH
        config_tools.CONFIG_PATH = config_path
        try:
            result = config_tools.update_config_sa_enable("true")
            self.assertEqual(result["status"], "success")
            
            with open(config_path, 'r') as f:
                content = f.read()
            self.assertIn('SA_ENABLE = "true"', content)
        finally:
            config_tools.CONFIG_PATH = original_config_path

    def test_update_config_apigee_org(self):
        config_path = os.path.join(self.test_dir, "config.py")
        with open(config_path, 'w') as f:
            f.write('APIGEE_HYB_ORG = "old_org"\n')
            
        original_config_path = config_tools.CONFIG_PATH
        config_tools.CONFIG_PATH = config_path
        try:
            result = config_tools.update_config_apigee_org("new_org")
            self.assertEqual(result["status"], "success")
            
            with open(config_path, 'r') as f:
                content = f.read()
            self.assertIn('APIGEE_HYB_ORG = "new_org"', content)
        finally:
            config_tools.CONFIG_PATH = original_config_path

    def test_check_developer_registry(self):
        dev_reg_file = os.path.join(self.registry_dir, "developer_registry.json")
        dummy_data = {
            "eval": [
                {"email": "dev@example.com"}
            ]
        }
        with open(dev_reg_file, 'w') as f:
            json.dump(dummy_data, f)
            
        result = config_tools.check_developer_registry("eval", "dev@example.com")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["found"])
        
        result = config_tools.check_developer_registry("eval", "other@example.com")
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["found"])

    def test_check_kvm_registry(self):
        """
        Bug Fix: Updated to use any() with dictionary key lookup to support KVM registry structure.
        """
        kvm_reg_file = os.path.join(self.registry_dir, "kvm_import_registry.json")
        dummy_data = {
            "eval": {
                "org": [{"name": "kvm1"}],
                "env1": [{"name": "kvm2"}]
            }
        }
        with open(kvm_reg_file, 'w') as f:
            json.dump(dummy_data, f)
            
        result = config_tools.check_kvm_registry("eval", "org", "kvm1")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["found"])
        
        result = config_tools.check_kvm_registry("eval", "env1", "kvm2")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["found"])
        
        result = config_tools.check_kvm_registry("eval", "env1", "missing_kvm")
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["found"])

if __name__ == '__main__':
    unittest.main()
