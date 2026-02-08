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
    """The Brain: Decides if we need data or just a chat."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    system_prompt = SystemMessage(content=f"""
    You are 'Shubh-Chintak', a CEO's mentor. 
    Today's Date is {today}.

    RULES:
    1. If the user asks for sales or data, you MUST respond with a JSON block and NOTHING ELSE.
    Format: {{"action": "get_sales_data", "date": "YYYY-MM-DD"}}
    
    2. If the user is just saying 'Hi' or asking a general question, respond as a mentor.
    
    3. Do NOT use tags like <function> or <tool>. Just raw text or the JSON block.
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
    """The Action: Manually calling the sheet tool."""
    last_message = state["messages"][-1].content
    try:
        # Extract date from the JSON block the LLM sent
        data = json.loads(last_message)
        target_date = data.get("date")
        
        # Call your sheet_manager function
        sheet_results = get_sales_data.invoke(target_date)
        
        return {"messages": [HumanMessage(content=f"Here is the data from the sheet: {sheet_results}. Now, analyze this for the CEO.")]}
    except Exception as e:
        return {"messages": [HumanMessage(content=f"Tell the CEO: I couldn't parse the data. Error: {str(e)}")]}

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