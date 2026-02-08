import os
import textwrap
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from scripts.graph_agent import app_graph
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
# Hardcoded Sandbox Number (To prevent "To/From same" errors)
TWILIO_BOT_NUMBER = 'whatsapp:+14155238886' 

# Initialize Client
try:
    client = Client(os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN"))
except Exception as e:
    print(f"⚠️ Twilio Init Error: {e}")

def send_long_message(body, to_number):
    """
    Splits a long message into smaller chunks (1500 chars) 
    and sends them sequentially to avoid Twilio errors.
    """
    # 1. Check if message is short enough
    if len(body) < 1600:
        client.messages.create(
            from_=TWILIO_BOT_NUMBER,
            body=body,
            to=to_number
        )
        return

    # 2. If too long, split it using textwrap
    # We use 1500 to leave wiggle room for metadata
    chunks = textwrap.wrap(body, width=1500, replace_whitespace=False, drop_whitespace=False)
    
    for i, chunk in enumerate(chunks):
        # Optional: Add (Part 1/3) to make it clear
        msg_part = f"[{i+1}/{len(chunks)}] {chunk}"
        client.messages.create(
            from_=TWILIO_BOT_NUMBER,
            body=msg_part,
            to=to_number
        )

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get('Body', '')
    sender_id = request.values.get('From', '')

    print(f"\n--- PROCESSING MESSAGE FROM {sender_id} ---")
    print("User says: ", incoming_msg)

    config = {"configurable": {"thread_id": sender_id}}
    input_state = {"messages": [("user", incoming_msg)]}

    try:
        # 1. Run the AI
        final_state = app_graph.invoke(input_state, config=config)
        final_answer = final_state["messages"][-1].content

        print("AI says: ", final_answer)
        
        # 2. Send (using the new splitter function)
        send_long_message(final_answer, sender_id)
        
        print("✅ Message pushed to WhatsApp successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        # Send a short error note to the user
        try:
            client.messages.create(from_=TWILIO_BOT_NUMBER, body="My response was too large to process.", to=sender_id)
        except:
            pass

    # 3. Always return 200 OK
    return str(MessagingResponse())

if __name__ == "__main__":
    app.run(port=7860, debug=True)
