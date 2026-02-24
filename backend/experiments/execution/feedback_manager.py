import json
import os
import uuid
from datetime import datetime

class FeedbackManager:
    def __init__(self, workspace_path):
        self.workspace_path = workspace_path
        self.feedback_file = os.path.join(workspace_path, "user_feedback.json")
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.workspace_path):
            os.makedirs(self.workspace_path, exist_ok=True)
        if not os.path.exists(self.feedback_file):
            with open(self.feedback_file, "w") as f:
                json.dump([], f)

    def add_feedback(self, feedback_type, message):
        """
        Adds a new feedback entry.
        feedback_type: 'risk', 'correction', 'suggestion'
        """
        self._ensure_file()
        
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "type": feedback_type,
            "message": message,
            "status": "pending" # pending, processed, ignored
        }
        
        with open(self.feedback_file, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
        
        data.append(entry)
        
        with open(self.feedback_file, "w") as f:
            json.dump(data, f, indent=2)
            
        return entry

    def get_pending_feedback(self):
        """Returns list of pending feedback items."""
        if not os.path.exists(self.feedback_file):
            return []
            
        with open(self.feedback_file, "r") as f:
            try:
                data = json.load(f)
            except:
                return []
                
        return [item for item in data if item["status"] == "pending"]

    def mark_processed(self, feedback_id, action_taken="processed"):
        """Marks feedback as processed/ignored."""
        if not os.path.exists(self.feedback_file):
            return
            
        with open(self.feedback_file, "r") as f:
            data = json.load(f)
            
        for item in data:
            if item["id"] == feedback_id:
                item["status"] = action_taken
                item["processed_at"] = datetime.now().isoformat()
                
        with open(self.feedback_file, "w") as f:
            json.dump(data, f, indent=2)
