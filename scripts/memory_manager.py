import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MEMORY_FILE = os.path.join(DATA_DIR, "user_memory_db.json")

def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def load_db():
    """Loads the entire JSON database."""
    _ensure_data_dir()
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_db(data):
    """Writes back to the JSON file."""
    _ensure_data_dir()
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_or_create_user(user_id):
    """Ensures the user exists in the DB with the correct schema."""
    data = load_db()
    
    if user_id not in data:
        current_time = datetime.now().isoformat()
        data[user_id] = {
            "phone_number": user_id,
            "conversation_history": [],
            "created_at": current_time,
            "last_interaction": current_time,
            "total_queries": 0
        }
        save_db(data)
    
    return data[user_id]

def update_memory(user_id, user_msg, bot_resp):
    """Updates the user's history and counters."""
    data = load_db()
    
    # Ensure user exists
    if user_id not in data:
        get_or_create_user(user_id)
        data = load_db() # Reload to get the new user

    # 1. Update Timestamps & Counters
    data[user_id]["last_interaction"] = datetime.now().isoformat()
    data[user_id]["total_queries"] += 1
    
    # 2. Append to History
    new_entry = {
        "user_message": user_msg,
        "bot_response": bot_resp,
        "timestamp": datetime.now().isoformat()
    }
    data[user_id]["conversation_history"].append(new_entry)
    
    # 3. Trim History (Keep last 10 to prevent token overflow)
    if len(data[user_id]["conversation_history"]) > 10:
        data[user_id]["conversation_history"] = data[user_id]["conversation_history"][-10:]
        
    save_db(data)

def get_context_string(user_id):
    """Formats the history into a string for the AI."""
    data = load_db()
    if user_id not in data:
        return ""
        
    history = data[user_id]["conversation_history"][-3:] # Get last 3 turns
    
    context = "\n--- PREVIOUS CONVERSATION CONTEXT ---\n"
    for turn in history:
        context += f"User: {turn['user_message']}\nBot: {turn['bot_response']}\n"
    context += "-------------------------------------\n"
    
    return context if history else ""