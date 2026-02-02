import pytest
import os
import shutil
import json
from unittest.mock import MagicMock, patch
from backend.execution.experiment_runner import ExperimentRunner

class TestExperimentRunner:
    """
    Test Suite for ExperimentRunner
    
    Tests cover:
    1. Initialization (Workspace creation, Git init)
    2. Dependency Analysis (filtering std libs)
    3. Commit Structure (Metadata verification)
    """

    @pytest.fixture
    def workspace(self, tmp_path):
        """Create a temporary workspace directory."""
        ws = tmp_path / "test_exp_workspace"
        ws.mkdir()
        return str(ws)

    @pytest.fixture
    def plan(self):
        return {
            "title": "Test Plan",
            "steps": [
                {
                    "name": "Step 1", 
                    "dependencies": [
                        {"name": "numpy", "type": "python_package", "status": "auto_installable"},
                        {"name": "os", "type": "python_package", "status": "auto_installable"} # Should be filtered
                    ]
                }
            ]
        }

    @pytest.fixture
    def runner(self, workspace, plan):
        # Patch internal agents to avoid real instantiation
        with patch('backend.execution.experiment_runner.CodingAgent'), \
             patch('backend.execution.experiment_runner.DataAnalysisAgent'), \
             patch('backend.execution.experiment_runner.ReviewAgent'), \
             patch('backend.execution.experiment_runner.FeedbackManager'):
            
            runner = ExperimentRunner(workspace, plan)
            return runner

    def test_initialization(self, runner, workspace):
        """Test that runner initializes workspace and git."""
        # Mock git commands
        runner._run_git_cmd = MagicMock(return_value=True)
        
        runner._init_workspace()
        
        # Check if plan.json is saved
        assert os.path.exists(os.path.join(workspace, "plan.json"))
        
        # Verify git init was called
        # Note: We mocked _run_git_cmd, so we check if it was called with init-like args
        # But subprocess.run("git", "init") is called directly in _init_workspace, not via _run_git_cmd
        # So we can't easily verify "git init" without mocking subprocess.run. 
        # However, we can verify the subsequent config calls which use _run_git_cmd.
        runner._run_git_cmd.assert_any_call(["config", "user.email", "agent@autoresearchlab.ai"])

    def test_setup_dependencies_filtering(self, runner):
        """Test that standard library modules are filtered out from requirements."""
        # The plan fixture has "numpy" and "os" as dependencies.
        # "os" is in the exclusion list.
        
        pip_packages = runner._setup_dependencies()
        
        assert "numpy" in pip_packages
        assert "os" not in pip_packages
        
        # Verify default analysis libs are added
        assert "pandas" in pip_packages
        assert "matplotlib" in pip_packages

    def test_commit_structured(self, runner):
        """Test that git commits include structured metadata."""
        runner._run_git_cmd = MagicMock(return_value=True)
        
        runner._commit_structured(
            step_id=1, 
            attempt=1, 
            plan="Run code", 
            scheme="Standard", 
            result="Success", 
            decision="Continue"
        )
        
        # Verify commit message format
        args, _ = runner._run_git_cmd.call_args
        command = args[0]
        assert command[0] == "commit"
        message = command[3]
        
        assert "METADATA_START" in message
        assert "METADATA_END" in message
        assert '"step": 1' in message
        assert '"result": "Success"' in message
