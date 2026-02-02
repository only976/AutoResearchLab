import pytest
from backend.tools.git_ops import GitOps

class TestGitOps:
    @pytest.fixture
    def git_ops(self, tmp_path):
        # Use tmp_path fixture from pytest for a temporary git repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        return GitOps(repo_path=str(repo_path))

    def test_initialization(self, git_ops):
        assert git_ops is not None
