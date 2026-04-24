import os
import unittest
from unittest.mock import patch, mock_open, MagicMock
from tools import execution_tools

class TestExecutionTools(unittest.TestCase):

    @patch('tools.execution_tools.subprocess.run')
    @patch('tools.execution_tools.glob.glob')
    @patch('tools.execution_tools.os.path.getctime')
    def test_run_transform_script_success(self, mock_getctime, mock_glob, mock_run):
        # Setup mocks
        mock_run.return_value = MagicMock(returncode=0)
        mock_glob.return_value = ["/mock/path/latest.log"]
        mock_getctime.return_value = 12345
        
        log_content = "[SUCCESS] Transformed KVM 1\n❌ ERROR failed to read\n⚠️ WARNING missing field"
        
        # Mock open specifically in execution_tools module
        with patch("tools.execution_tools.open", mock_open(read_data=log_content)):
            result = execution_tools.run_transform_script()
            
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["metrics"]["successfully_transformed"], 1)
        self.assertEqual(result["metrics"]["errors_encountered"], 1)
        self.assertEqual(result["metrics"]["warnings"], 1)

    @patch('tools.execution_tools.subprocess.run')
    def test_run_transform_script_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        
        result = execution_tools.run_transform_script()
        
        self.assertEqual(result["status"], "error")
        self.assertIn("failed to execute", result["message"])

    @patch('tools.execution_tools.subprocess.run')
    @patch('tools.execution_tools.glob.glob')
    def test_run_surgical_delete_script_success(self, mock_glob, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        mock_glob.return_value = [] # Simulate missing log for simplicity
        
        result = execution_tools.run_surgical_delete_script("my-org", "env1", "kvm1")
        
        self.assertEqual(result["status"], "success")
        self.assertIn("Script ran", result["message"])
        
        # Verify subprocess arguments
        called_args = mock_run.call_args[0][0]
        self.assertIn("my-org", called_args)
        self.assertIn("env1", called_args)
        self.assertIn("kvm1", called_args)

if __name__ == '__main__':
    unittest.main()
