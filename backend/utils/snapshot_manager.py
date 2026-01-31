import os
import json
from datetime import datetime

SNAPSHOT_DIR = os.path.join(os.getcwd(), "data", "cache", "snapshots")

def save_snapshot(refinement_data, results, custom_name=None):
    """Saves the current session state (refinement + ideas) to a JSON file."""
    if not os.path.exists(SNAPSHOT_DIR):
        os.makedirs(SNAPSHOT_DIR)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Generate a default name from the first topic title if not provided
    if not custom_name:
        if results and len(results) > 0:
            # results is a list of dicts: {'topic': ..., 'ideas_data': ...}
            title = results[0].get("topic", {}).get("title", "untitled")
            # Sanitize title
            safe_title = "".join([c if c.isalnum() else "_" for c in title])[:30]
            custom_name = f"{timestamp}_{safe_title}"
        else:
            custom_name = f"{timestamp}_empty"
            
    # Ensure .json extension
    if not custom_name.endswith(".json"):
        custom_name += ".json"
            
    filepath = os.path.join(SNAPSHOT_DIR, custom_name)
    
    data = {
        "timestamp": timestamp,
        "refinement_data": refinement_data,
        "results": results
    }
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
        
    return custom_name

def list_snapshots():
    """Returns a list of snapshot filenames sorted by modification time (newest first)."""
    if not os.path.exists(SNAPSHOT_DIR):
        return []
        
    files = [f for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".json")]
    # Sort by mtime descending
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SNAPSHOT_DIR, x)), reverse=True)
    return files

def load_snapshot(filename):
    """Loads a snapshot JSON file."""
    filepath = os.path.join(SNAPSHOT_DIR, filename)
    if not os.path.exists(filepath):
        return None
        
    with open(filepath, "r") as f:
        return json.load(f)
