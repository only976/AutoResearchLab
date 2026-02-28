import os
import uuid
from datetime import datetime

from backend.db.repository import (
    add_feedback as db_add_feedback,
    get_pending_feedback as db_get_pending_feedback,
    mark_feedback_processed as db_mark_feedback_processed,
)

class FeedbackManager:
    def __init__(self, workspace_path):
        self.workspace_path = workspace_path
        self.exp_id = os.path.basename(workspace_path)
        self._ensure_workspace()

    def _ensure_workspace(self):
        if not os.path.exists(self.workspace_path):
            os.makedirs(self.workspace_path, exist_ok=True)

    def add_feedback(self, feedback_type, message):
        """
        Adds a new feedback entry.
        feedback_type: 'risk', 'correction', 'suggestion'
        """
        self._ensure_workspace()
        
        feedback_id = str(uuid.uuid4())
        entry = {
            "id": feedback_id,
            "timestamp": datetime.now().isoformat(),
            "type": feedback_type,
            "message": message,
            "status": "pending" # pending, processed, ignored
        }

        db_add_feedback(self.exp_id, feedback_id, feedback_type, message)
        return entry

    def get_pending_feedback(self):
        """Returns list of pending feedback items."""
        return db_get_pending_feedback(self.exp_id)

    def mark_processed(self, feedback_id, action_taken="processed"):
        """Marks feedback as processed/ignored."""
        db_mark_feedback_processed(self.exp_id, feedback_id, action_taken)
