import os
import json
from datetime import datetime
from typing import TypedDict, Annotated, List
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

# Internal Imports
from scripts.sheet_manager import get_sales_data

load_dotenv()

# 1. State Definition
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

# 2. Setup LLM (We don't 'bind_tools' here to avoid the Groq 400 error)
llm = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model_name="llama-3.3-70b-versatile",
    temperature=0
)

# 3. Nodes
def call_mentor(state: AgentState):
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    first_day_of_year = today.strftime("%Y-01-01")

    system_prompt = SystemMessage(content=f"""
    You are 'Shubh-Chintak', a CEO's mentor.
    Current Date: {today_str}

    HOW TO FETCH DATA:
    - Single Day: {{"action": "get_sales_data", "start_date": "2025-08-22"}}
    - A Specific Month: Use the 1st and the last day of that month.
    - This Year so far: {{"action": "get_sales_data", "start_date": "{first_day_of_year}", "end_date": "{today_str}"}}
    - Custom Range: Use 'start_date' and 'end_date'.
    - Follow-up: If the user says "that month", look at the previous message to find the year/month mentioned.

    If the user asks for data, respond ONLY with the JSON block.
    If the user asks for analysis, be a wise mentor.
    """)
    
    response = llm.invoke([system_prompt] + state["messages"])
    return {"messages": [response]}

def tool_router(state: AgentState):
    """The n8n Router: Logic to decide where to go next."""
    last_message = state["messages"][-1].content
    
    if '"action": "get_sales_data"' in last_message:
        return "call_sheet"
    return END

def call_sheet_node(state: AgentState):
    last_message = state["messages"][-1].content
    try:
        data = json.loads(last_message)
        # Extract both dates if they exist
        s_date = data.get("start_date")
        e_date = data.get("end_date", None) # Default to None if not provided
        
        # Call the tool with both arguments
        sheet_results = get_sales_data.invoke({"start_date": s_date, "end_date": e_date})
        
        return {"messages": [HumanMessage(content=f"Data: {sheet_results}. Summarize and provide mentor advice.")]}
    except Exception as e:
        return {"messages": [HumanMessage(content=f"Technical error: {str(e)}")]}

# 4. Build the Graph
workflow = StateGraph(AgentState)

workflow.add_node("mentor", call_mentor)
workflow.add_node("call_sheet", call_sheet_node)

workflow.set_entry_point("mentor")

workflow.add_conditional_edges(
    "mentor",
    tool_router,
    {
        "call_sheet": "call_sheet",
        END: END
    }
)

# After sheet data is fetched, go back to mentor for the final analysis
workflow.add_edge("call_sheet", "mentor")

app_graph = workflow.compile()
