import os
import json
import time
from datetime import datetime
from typing import TypedDict, Annotated, List
from dotenv import load_dotenv
import re
from datetime import datetime, timedelta
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from scripts.sheet_manager import get_sales_data
from scripts import memory_manager

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

MODEL_NAME = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

llm = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model_name=MODEL_NAME,
    max_tokens=600,
    temperature=0,
)

def call_mentor(state: AgentState):
    today = datetime.now()
    
    system_content = f"""You are *SalesGuru* 🤖 - An Elite AI Business Analyst and Strategic Mentor to the CEO.

## YOUR CORE IDENTITY:
- You act as a fractional Chief Data Analyst. You answer real-world executive questions (Revenue trends, Top performers, Regional comparisons, Product analysis, etc.).
- You speak with warmth, extreme professional clarity, and strategic foresight.
- Always answer exactly what the CEO asks. No fluff.

Today is {today.strftime("%Y-%m-%d")}.

## 🛑 ZERO-HALLUCINATION POLICY:
1. **NEVER guess data.** If you don't have the hard numbers in your 'SYSTEM_DATA_FEED', you must trigger the tool.
2. **DO NOT** write "I am checking..." or "Let me calculate...". 
3. **ONLY** output the JSON action to trigger the tool when data is missing.

## 🧠 EXECUTIVE INTENT & TOOL TRIGGERS:
Map the CEO's question to the correct JSON tool call. Use wide dates (e.g., "2010-01-01" to "2030-12-31") for lifetime/all-time queries.

- **Specific Order Lookup:**
  {{"action": "get_sales_data", "order_id": "ID_HERE"}}
- **Regional/Location Analysis:**
  {{"action": "get_sales_data", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "location": "State/City Name"}}
- **Top Performers (Products, Customers, Categories, Sub-categories):**
  {{"action": "get_sales_data", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "group_by": "Column Name", "top_k": 5}}
- **General Sales / Trend Analysis:**
  {{"action": "get_sales_data", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}}

## 🚨 CRITICAL DATA RULES:
1. **THE HISTORIAN RULE**: The CEO is analyzing historical datasets. Use exactly the year they ask for. Do not say "We don't have data for the future" or "That is in the past."
2. **PROXY METRICS**: If the CEO asks for "Profit" but the feed only gives "Sales", analyze Sales and politely note that you are using Revenue as the primary metric.

## BEHAVIOR & FORMATTING RULES:
- **DATA VISUAL**: When providing metrics, ALWAYS use ASCII bars (█, ▓, ▒) inside ``` blocks to make it look like a dashboard.
  - Show at most 5–7 rows/bars.
  - Each bar line MUST include a short label, a bar, and the value on the same line.
  - Bars must be short: maximum 25 characters wide (truncate longer bars, do NOT repeat the character across the full screen).
- **MENTOR INSIGHT**: Follow the data with 1 Diagnostic insight (Why it matters) and 1 Prescriptive action (What we should do next).
- **CONCISE**: Keep the full WhatsApp reply under 1200 characters for readability. 

## RESPONSE STRUCTURE:
1. **Executive Summary:** Warm, 1-sentence acknowledgment.
2. **The Numbers:** ASCII visualization of the tool's data.
3. **Strategic Insight:** "The data shows..." + 1 actionable recommendation.
4. **Next Step:** Offer a logical follow-up analysis.

## LIVE DATA REQUIREMENT (VERY IMPORTANT):
- For **every** new question from the CEO, even if it looks similar to a previous one, you MUST trigger a fresh JSON tool call using the formats above.
- **Never reuse or rely on old numeric answers from memory.** Always ask the `get_sales_data` tool again so that the numbers reflect the latest Google Sheet contents.
- If the question can be answered using the sales sheet in any way, you MUST emit one or more JSON tool calls as your entire response.
"""

    # Build the full message list for the LLM:
    # 1) System instructions (above)
    # 2) All prior conversation messages from the graph state
    messages: List[BaseMessage] = [SystemMessage(content=system_content)]
    messages.extend(state["messages"])

    # Call the LLM once for this step in the graph, with simple
    # retry logic to handle transient 429 rate-limit errors.
    retries = 3
    delay = 1.0
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            ai_reply = llm.invoke(messages)
            break
        except Exception as e:
            # Groq / HTTP 429 style errors often mention "rate limit" or 429
            if "rate limit" in str(e).lower() or "429" in str(e):
                last_err = e
                time.sleep(delay)
                delay *= 2
                continue
            # For any other error, don't keep retrying here
            raise
    else:
        # If we exhausted retries on rate limit, return a graceful message
        fallback = AIMessage(
            content=(
                "I'm temporarily at capacity processing analytics requests. "
                "Please wait a few seconds and ask your question again."
            )
        )
        return {"messages": [fallback]}

    # The graph expects us to return a dict with a "messages" key
    return {"messages": [ai_reply]}


def tool_router(state: AgentState):
    """
    Decide whether we should call the Google Sheet tool.

    We look at the *latest* AI message and check if it emitted a JSON blob
    with either an `action` or an `order_id`. This keeps behaviour compatible
    with your existing prompt format while ensuring a fresh tool call for each query.
    """
    last_msg = state["messages"][-1]
    content = getattr(last_msg, "content", "")

    # Trigger if the AI proposed a tool call-style JSON
    if isinstance(last_msg, AIMessage) and "{" in content and ("order_id" in content or "action" in content):
        return "call_sheet"

    return END

def call_sheet_node(state: AgentState):
    last_message = state["messages"][-1].content
    # Find ALL JSON blocks (for comparisons)
    json_blobs = re.findall(r'\{.*?\}', last_message, re.DOTALL)
    
    combined_results = ""
    for blob in json_blobs:
        try:
            args = json.loads(blob)
            # Call your actual sheet tool here
            raw_data = get_sales_data.invoke(args)
            query_label = args.get('start_date') or args.get('order_id') or args.get('location') or args.get('group_by') or 'QUERY'
            combined_results += f"\n--- DATA FOR {query_label} ---\n{raw_data}\n"
        except Exception as e:
            combined_results += f"\nError processing {blob}: {str(e)}"

    # Send this BACK to the mentor
    return {"messages": [HumanMessage(content=f"SYSTEM_DATA_FEED:\n{combined_results}")]}


# BUILD GRAPH
workflow = StateGraph(AgentState)
workflow.add_node("mentor", call_mentor)
workflow.add_node("call_sheet", call_sheet_node)
workflow.set_entry_point("mentor")

workflow.add_conditional_edges("mentor", tool_router, {"call_sheet": "call_sheet", END: END})
workflow.add_edge("call_sheet", "mentor")

app_graph = workflow.compile()


# --- THE EXECUTION WRAPPER ---
def get_mentor_reply(user_id: str, user_msg: str):
    """
    This is the entry point called by main.py.
    It handles:
    1. Loading user-specific history from JSON.
    2. Running the LangGraph.
    3. Filtering for the final AI response (not the data feed).
    4. Saving the new response back to JSON.
    """
    # 1. Load context from JSON memory manager
    user_data = memory_manager.get_or_create_user(user_id)
    # Get last 2 turns to keep token size compact and prevent Groq free tier rate limit
    history = user_data.get("conversation_history", [])[-2:] 
    
    # 2. Convert JSON history to LangChain Message objects
    langchain_history = []
    for turn in history:
        langchain_history.append(HumanMessage(content=turn["user_message"]))
        langchain_history.append(AIMessage(content=turn["bot_response"]))
    
    # 3. Add the new user message
    langchain_history.append(HumanMessage(content=user_msg))
    
    # 4. Run the Graph safely
    bot_reply = None
    try:
        final_state = app_graph.invoke({"messages": langchain_history})
        
        # 5. Extract the LAST AI Message
        for m in reversed(final_state["messages"]):
            if isinstance(m, AIMessage):
                if "{" in m.content and "action" in m.content:
                    continue
                bot_reply = m.content
                break
    except Exception as e:
        print(f"⚠️ Graph execution exception: {e}")
        if "429" in str(e) or "rate limit" in str(e).lower() or "tokens" in str(e).lower():
            bot_reply = "⚡ SalesGuru is experiencing a brief rate limit from the free LLM API tier. Please wait 5-10 seconds and send your question again!"
        else:
            bot_reply = "📊 I experienced a temporary glitch fetching the sales data feed. Please try asking your question again in a moment."

    # Fallback if something went wrong in the graph
    if not bot_reply:
        bot_reply = "📊 I've processed the data, but I'm having trouble formatting the insight. Could you try asking that again?"

    # 6. Save back to JSON Memory
    memory_manager.update_memory(user_id, user_msg, bot_reply)
    
    return bot_reply