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
            # results is a list of dicts: {'topic': ..., 'ideas': ...}
            # Note: The key in results is 'topic', and inside topic we expect 'title'
            # But sometimes it might be nested differently depending on how it's passed
            topic_data = results[0].get("topic", {})
            # Handle case where topic_data might be a string (though it should be dict)
            if isinstance(topic_data, dict):
                title = topic_data.get("title", "untitled")
            else:
                title = "untitled"
                
            # Sanitize title: keep alphanumeric and spaces, replace others with underscore
            # Limit length to 50 chars for better readability
            safe_title = "".join([c if c.isalnum() or c == ' ' else "_" for c in title])
            safe_title = "_".join(safe_title.split()) # collapse multiple spaces/underscores
            safe_title = safe_title[:50]
            
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
    """Returns a list of snapshot metadata sorted by modification time (newest first)."""
    if not os.path.exists(SNAPSHOT_DIR):
        return []
        
    files = [f for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".json")]
    # Sort by mtime descending
    files.sort(key=lambda x: os.path.getmtime(os.path.join(SNAPSHOT_DIR, x)), reverse=True)
    
    snapshots = []
    for f in files:
        try:
            # Parse filename format: YYYYMMDD_HHMMSS_Title.json
            parts = f.replace(".json", "").split("_", 2)
            timestamp_str = ""
            title = f
            
            if len(parts) >= 2:
                timestamp_str = f"{parts[0]} {parts[1][:2]}:{parts[1][2:4]}"
                if len(parts) > 2:
                    # Replace underscores with spaces for display, but be careful if original title had underscores
                    # The simple split above limits to 2 splits, so parts[2] is the rest of the string
                    # We can try to make it look nicer
                    title_part = parts[2].replace(".json", "")
                    title = title_part.replace("_", " ")
            
            snapshots.append({
                "filename": f,
                "timestamp": timestamp_str,
                "title": title,
                "path": os.path.join(SNAPSHOT_DIR, f)
            })
        except Exception:
            snapshots.append({
                "filename": f,
                "timestamp": "",
                "title": f,
                "path": os.path.join(SNAPSHOT_DIR, f)
            })
            
    return snapshots

def load_snapshot(filename):
    """Loads a snapshot JSON file."""
    filepath = os.path.join(SNAPSHOT_DIR, filename)
    if not os.path.exists(filepath):
        return None
        
    with open(filepath, "r") as f:
        return json.load(f)
