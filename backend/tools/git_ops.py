import os
import subprocess
from typing import List, Optional

class GitOps:
    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def _run(self, args: List[str], check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

    def is_repo(self) -> bool:
        return os.path.exists(os.path.join(self.repo_path, ".git"))

    def init_repo(self) -> bool:
        if self.is_repo():
            return True
        res = self._run(["init"])
        return res.returncode == 0

    def rollback_last_commit(self, steps: int = 1) -> bool:
        if not self.is_repo():
            return False
        res = self._run(["reset", "--hard", f"HEAD~{steps}"])
        return res.returncode == 0

def rollback_last_commit(repo_path: str, steps: int = 1) -> bool:
    return GitOps(repo_path).rollback_last_commit(steps=steps)
