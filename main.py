import os
import sys
import textwrap
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from scripts import graph_agent, memory_manager
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

load_dotenv()
app = Flask(__name__)

TWILIO_BOT_NUMBER = os.getenv('TWILIO_BOT_NUMBER', 'whatsapp:+14155238886')

client = None
account_sid = os.getenv("TWILIO_SID")
auth_token = os.getenv("TWILIO_TOKEN")

if account_sid and auth_token:
    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        print(f"⚠️ Twilio Init Warning: {e}")

def send_long_message(body, to_number):
    if client and account_sid and auth_token:
        try:
            if len(body) < 1600:
                client.messages.create(from_=TWILIO_BOT_NUMBER, body=body, to=to_number)
                return True
            chunks = textwrap.wrap(body, width=1500, replace_whitespace=False, drop_whitespace=False)
            for i, chunk in enumerate(chunks):
                client.messages.create(from_=TWILIO_BOT_NUMBER, body=f"[{i+1}/{len(chunks)}]\n{chunk}", to=to_number)
            return True
        except Exception as e:
            print(f"⚠️ Twilio REST API send failed: {e}")
            return False
    return False

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get('Body', '')
    sender_id = request.values.get('From', '')

    print(f"📩 {sender_id}: {incoming_msg}")

    try:
        # 1. Update/Clean Memory
        memory_manager.get_or_create_user(sender_id)
        
        # 2. Get AI Response
        final_answer = graph_agent.get_mentor_reply(sender_id, incoming_msg)
        
        # 3. Deliver via REST API if configured, else fallback to direct TwiML response
        sent = send_long_message(final_answer, sender_id)
        
        resp = MessagingResponse()
        if not sent:
            # Fallback to standard TwiML response if REST API fails or is unconfigured
            resp.message(final_answer)
            
        return str(resp)

    except Exception as e:
        print(f"❌ Error in webhook: {e}")
        resp = MessagingResponse()
        resp.message("I'm having trouble accessing the records. One moment.")
        return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=True)