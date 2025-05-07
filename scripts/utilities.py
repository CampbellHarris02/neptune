import json
import os

# --- Utilities ---
def load_json(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)