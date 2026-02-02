import pytest
from backend.engine.orchestrator import Orchestrator

class TestOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        # Assuming Orchestrator can be instantiated without args or with simple args
        # Check constructor if needed.
        return Orchestrator()

    def test_initialization(self, orchestrator):
        assert orchestrator is not None
