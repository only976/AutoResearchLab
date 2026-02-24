import pytest
from backend.sandbox.docker_sandbox import DockerSandbox

class TestDockerSandbox:
    @pytest.fixture
    def sandbox(self):
        # DockerSandbox might require specific args
        return DockerSandbox()

    def test_initialization(self, sandbox):
        assert sandbox is not None
