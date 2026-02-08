import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Import the Graph we just built
from scripts.graph_agent import app_graph 

load_dotenv()
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    # 1. Get Incoming Data
    incoming_msg = request.values.get("Body", "").strip()
    sender_number = request.values.get("From", "unknown")
    
    print(f"📩 Message from {sender_number}: {incoming_msg}")

    # 2. Config for Memory (Session ID = Phone Number)
    config = {"configurable": {"thread_id": sender_number}}
    
    # 3. Run the LangGraph
    # We pass the new message into the state
    input_state = {
        "user_query": incoming_msg,
        "messages": [HumanMessage(content=incoming_msg)]
    }
    
    final_state = app_graph.invoke(input_state, config=config)
    
    # 4. Extract AI Reply
    ai_reply_text = final_state["messages"][-1].content
    visual_needed = final_state.get("visual_needed", False)

    # 5. Send Response to Twilio
    resp = MessagingResponse()
    msg = resp.message(ai_reply_text)
    
    # If a chart was requested and scraper ran successfully
    if visual_needed and os.path.exists("report.png"):
        # Note: In production, you need a public URL for the image.
        # For local testing, ngrok handles this if configured, or Twilio requires a public URL.
        # msg.media("http://your-public-url.com/report.png")
        msg.body(ai_reply_text + "\n\n(📸 Dashboard screenshot saved on server)")

    return str(resp)

if __name__ == "__main__":
    app.run(port=7860, debug=True)