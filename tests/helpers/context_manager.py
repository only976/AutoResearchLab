import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

class TestContextManager:
    """
    Manages test contexts and mock data for backend testing.
    Stores data in a separate directory from production data.
    """
    __test__ = False
    
    def __init__(self, storage_dir: str = "data/test_data"):
        self.storage_dir = Path(os.path.abspath(storage_dir))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.fixtures_dir = Path(os.path.abspath("tests/fixtures"))
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)

    def save_context(self, case_id: str, data: Dict[str, Any], category: str = "general"):
        """
        Save context data for a specific test case.
        
        Args:
            case_id: Unique identifier for the test case
            data: Dictionary containing context data (inputs, expected outputs, state)
            category: Sub-directory for organization (e.g., 'agents', 'runner')
        """
        target_dir = self.storage_dir / category
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = target_dir / f"{case_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(file_path)

    def load_context(self, case_id: str, category: str = "general") -> Dict[str, Any]:
        """Load context data for a test case."""
        file_path = self.storage_dir / category / f"{case_id}.json"
        if not file_path.exists():
            # Fallback to fixtures if not found in test_data
            fixture_path = self.fixtures_dir / category / f"{case_id}.json"
            if fixture_path.exists():
                file_path = fixture_path
            else:
                raise FileNotFoundError(f"Context {case_id} not found in {file_path} or fixtures.")
        
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def snapshot_execution_state(self, source_dir: str, case_id: str):
        """
        Snapshot a real execution directory (e.g. data/experiments/exp_123) 
        into test storage for reproduction.
        """
        source = Path(source_dir)
        target = self.storage_dir / "snapshots" / case_id
        
        if target.exists():
            shutil.rmtree(target)
            
        shutil.copytree(source, target)
        return str(target)

    def get_snapshot_path(self, case_id: str) -> Path:
        """Get path to a stored snapshot."""
        return self.storage_dir / "snapshots" / case_id
