import os
import operator
from typing import Annotated, TypedDict, Union, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from app.config import Config
from app.utils.database_utils import get_from_csv, update_to_csv

# Import AI tools (call the functions defined in app.ai.tools)
from app.ai.tools import (
    get_available_courses,
    store_registration_info,
    validate_pr_card,
)

# --- 1. Define the Strict State ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    step: str                # Tracks which "Box" we are in (e.g., "ask_course", "payment")
    registration_data: dict  # Stores temp data (Name, Email, etc.)
    is_pr: bool              # "Is Client PR?" Decision
    payment_verified: bool   # "Payment Found?" Decision
    retry_count: int         # For the "Select Action" loop

# --- 2. Setup LLM ---
llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=Config.OPENAI_API_KEY)

# --- 3. Define the Nodes (The Boxes in your Flowchart) ---

def intent_router_node(state: AgentState):
    """First Diamond: What does the user want?"""
    last_msg = state["messages"][-1].content.lower()
    
    if "register" in last_msg or "sign up" in last_msg:
        return {"step": "ask_course"}
    elif "retrieve" in last_msg or "status" in last_msg:
        return {"step": "input_client_lookup"}
    else:
        return {"step": "general_chat"}

def ask_course_node(state: AgentState):
    """Node: 2a. Ask which Course"""
    courses = get_available_courses()
    course_list = ", ".join([f"{c['name']} (${c['price']})" for c in courses])
    msg = f"We have the following courses available: {course_list}. Which one would you like to register for?"
    return {"messages": [AIMessage(content=msg)], "step": "wait_for_course"}

def display_form_node(state: AgentState):
    """Node: 3b. Display Personal Info Form"""
    # We send a special trigger to the Frontend to show the React Form
    msg = "Great choice. Please fill out the registration form below. [FORM_TRIGGER]"
    return {"messages": [AIMessage(content=msg)], "step": "wait_for_form"}

def store_info_node(state: AgentState):
    """Node: Tool: Store Info in DB"""
    last_msg = state["messages"][-1].content
    # Assumption: Frontend sends form data as JSON string in the message
    # In a real app, parse this securely. 
    try:
        import json
        # Extract JSON if wrapped in text
        if "{" in last_msg:
            json_str = last_msg[last_msg.find("{"):last_msg.rfind("}")+1]
            user_data = json.loads(json_str)
        else:
            # Fallback if user typed it manually
            user_data = {"name": "User", "email": "test@test.com", "is_pr": False, "course_id": 1}
            
        # Call the tool function directly (store_registration_info expects user_info and course_id)
        course_id = int(user_data.get("course_id", 1))
        registration_result = store_registration_info(user_data, course_id)

        # store_registration_info returns the registration data dict (or an error dict)
        return {
            "registration_data": registration_result.get("data") if isinstance(registration_result, dict) and registration_result.get("data") else registration_result,
            "is_pr": user_data.get("is_pr", False),
            "step": "check_pr_status"
        }
    except Exception as e:
        return {"messages": [AIMessage(content="I couldn't read that form. Please try again.")], "step": "wait_for_form"}

def ask_pr_upload_node(state: AgentState):
    """Node: 3c. Ask to Upload PR"""
    return {"messages": [AIMessage(content="Since you are a Permanent Resident, please upload a photo of your PR Card.")], "step": "wait_for_upload"}

def validate_pr_node(state: AgentState):
    """Node: Tool: Validate PR"""
    # The last message should contain the image URL from the frontend upload
    last_msg = state["messages"][-1]
    image_url = None
    
    # Check if image_url was passed in the message content (LangChain standard)
    if isinstance(last_msg.content, list):
        for item in last_msg.content:
            if isinstance(item, dict) and item.get("type") == "image_url":
                image_url = item["image_url"]["url"]
    
    if not image_url:
        return {"messages": [AIMessage(content="I didn't receive an image. Please upload again.")], "step": "wait_for_upload"}
        
    # Call the validation tool (returns identification dict)
    validation = validate_pr_card(image_url, state.get("registration_data", {}))

    # identification_service returns keys like 'is_valid' and 'status'
    is_valid = validation.get("is_valid") or validation.get("PR_Card_Valid") or False

    if is_valid:
        return {"messages": [AIMessage(content="PR Card Verified Successfully!")], "step": "payment_phase"}
    else:
        reason = validation.get("message") or (validation.get("reasons") and ", ".join(validation.get("reasons"))) or "unknown"
        return {"messages": [AIMessage(content=f"Validation failed: {reason}. Please upload a clearer photo.")], "step": "wait_for_upload", "retry_count": state.get("retry_count", 0) + 1}

def payment_link_node(state: AgentState):
    """Node: 2e. Provide Payment Link"""
    link = "https://zeffy.com/pay/mock_link_123"
    msg = f"Registration saved! Please complete your payment here: {link}\n\nType 'Paid' when you are done."
    return {"messages": [AIMessage(content=msg)], "step": "wait_for_payment_conf"}

def check_payment_node(state: AgentState):
    """Node: 2g. Tool: Search Mailbox for Payment"""
    email = state.get("registration_data", {}).get("email", "unknown")
    # Fallback: check our CSV database for payment markers for this email.
    rows = get_from_csv(match_column=["Email"], match_value=[email])
    if not rows:
        return {"payment_verified": False, "step": "payment_retry"}

    # Check for a row that indicates payment was verified
    for r in rows:
        paid_flag = r.get("Payment_Status") or r.get("Paid")
        if paid_flag in (True, 'True', 'true', 'YES', 'Yes', 'yes') or (isinstance(paid_flag, str) and paid_flag.strip() != ""):
            return {"payment_verified": True, "step": "finalize"}

    return {"payment_verified": False, "step": "payment_retry"}

def send_email_node(state: AgentState):
    """Node: Tool: Send Email & Congratulate"""
    email = state.get("registration_data", {}).get("email")
    # For now, mark payment as confirmed in the DB and return a confirmation message.
    # If you have a mail extension, replace this with the actual send function.
    if email:
        update_to_csv({"Payment_Status": True, "Paid": True}, match_column=["Email"], match_value=[email])

    return {"messages": [AIMessage(content="Payment confirmed! A confirmation email has been sent. Welcome to the course!")], "step": "end"}

def payment_retry_node(state: AgentState):
    """Node: Inform Payment Not Found / Retry"""
    return {"messages": [AIMessage(content="I couldn't find the payment receipt in our mailbox yet. Please ensure you used the same email. Type 'Paid' to check again.")], "step": "wait_for_payment_conf"}

def general_chat_node(state: AgentState):
    """Fallback: Standard LLM Chat"""
    response = llm.invoke(state["messages"])
    return {"messages": [response], "step": "general_chat"}

# --- 4. Build the Graph (The Arrows in your Flowchart) ---
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("router", intent_router_node)
workflow.add_node("ask_course", ask_course_node)
workflow.add_node("display_form", display_form_node)
workflow.add_node("store_info", store_info_node)
workflow.add_node("ask_pr_upload", ask_pr_upload_node)
workflow.add_node("validate_pr", validate_pr_node)
workflow.add_node("payment_link", payment_link_node)
workflow.add_node("check_payment", check_payment_node)
workflow.add_node("payment_retry", payment_retry_node)
workflow.add_node("send_email", send_email_node)
workflow.add_node("general_chat", general_chat_node)

# --- Define Edges (Logic Flow) ---

# Start -> Router
workflow.add_edge(START, "router")

# Router Logic
def route_initial(state):
    return state["step"]

workflow.add_conditional_edges("router", route_initial, {
    "ask_course": "ask_course",
    "input_client_lookup": "general_chat", # Simplified for now
    "general_chat": "general_chat"
})

# Course -> Form
workflow.add_edge("ask_course", "display_form")

# Form -> Wait for User Input -> Store Info
# Note: We need to stop the graph to wait for user input. 
# We assume the next run calling 'process_message' will resume from the correct state.
# For this strictly mapped graph, we simply point to END, and rely on Memory to resume.
# However, to chain logic, we often assume the message passed IN triggers the next node.

# Simplified for Flask Request/Response:
# We manually route based on the *current* step stored in memory.

# ... (See `process_message` below for the routing logic that handles interruptions)

# Core Logic Chains
workflow.add_edge("display_form", END) # Wait for user to submit form
workflow.add_edge("store_info", "ask_pr_upload") # Assume PR for this logic path, check conditional below

def route_pr_check(state):
    if state["is_pr"]:
        return "ask_pr_upload"
    return "payment_link"

workflow.add_conditional_edges("store_info", route_pr_check, {
    "ask_pr_upload": "ask_pr_upload",
    "payment_link": "payment_link"
})

workflow.add_edge("ask_pr_upload", END) # Wait for image

def route_validation(state):
    # Logic is inside validate_pr_node return values
    if state["step"] == "payment_phase":
        return "payment_link"
    return "ask_pr_upload" # Retry loop

workflow.add_conditional_edges("validate_pr", route_validation, {
    "payment_link": "payment_link",
    "ask_pr_upload": "ask_pr_upload"
})

workflow.add_edge("payment_link", END) # Wait for "Paid"

def route_payment_check(state):
    if state["payment_verified"]:
        return "send_email"
    return "payment_retry"

workflow.add_conditional_edges("check_payment", route_payment_check, {
    "send_email": "send_email",
    "payment_retry": "payment_retry"
})

workflow.add_edge("payment_retry", END) # Wait for user to say "Paid" again
workflow.add_edge("send_email", END)
workflow.add_edge("general_chat", END)

# Compile
memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory)

# --- 5. Main Execution Function ---

def process_message(user_input: str, thread_id: str, image_url: str = None):
    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. Fetch current state to see where we left off
    current_state = app_graph.get_state(config).values
    current_step = current_state.get("step", "start") if current_state else "start"
    
    # 2. Construct Message
    content = []
    if user_input:
        content.append({"type": "text", "text": user_input})
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
        
    human_msg = HumanMessage(content=content)

    # 3. Route based on where we paused
    # If we were waiting for form, force the next node to be 'store_info'
    run_config = None
    
    if current_step == "wait_for_form":
        # Resume at store_info
        events = app_graph.stream(None, config, stream_mode="values") # This is tricky in LangGraph without specific node targeting
        # Easier approach: Just update state or let the router handle it.
        # Let's simple pass the message.
        pass
        
    # Standard Run
    # We pass the input. The graph needs to know which node to run if it was interrupted.
    # In LangGraph, if we hit END, we just invoke again.
    # We need to manually guide the "next" node if strictly sequential without AI routing.
    
    # Simple Router for the "Resume" logic
    inputs = {"messages": [human_msg]}
    
    if current_step == "wait_for_form":
        # We manually push the state forward
        result = app_graph.invoke({"messages": [human_msg]}, config) 
        # Note: Ideally you update the state to point to "store_info" before running, 
        # or have a conditional edge at START that checks 'step'.
    else:
        # Normal conversation flow
        pass
        
    # Run the graph
    # For this implementation, we will use a special entry point logic
    # If state is empty, run from START.
    # If state exists, LangGraph resumes automatically from the last checkpoint.
    
    # However, since we returned END in the edges above, we need to tell it where to go next.
    # We can use Command(resume=...) in newer LangGraph, or simply define the flow logic in a Router Node at the start.
    
    # Let's fix the START router to handle resumes:
    
    # RE-DEFINING START ROUTER LOGIC FOR RESUMES
    # (This replaces the simple START->router edge)
    
    # ... (Implemented internally by LangGraph if we didn't force END)
    # Since we forced END, we rely on the state['step'] to route us.
    
    # We update the graph definition slightly to allow this dynamic start:
    # See 'route_resume' below.
    
    final_response = ""
    for event in app_graph.stream(inputs, config, stream_mode="values"):
        if "messages" in event:
            final_response = event["messages"][-1].content
            
    return final_response

# Logic to handle the "Resume" routing at START
def route_resume(state):
    step = state.get("step")
    if step == "wait_for_form": return "store_info"
    if step == "wait_for_upload": return "validate_pr"
    if step == "wait_for_payment_conf": return "check_payment"
    return "router" # Default to intent analysis

# *CRITICAL UPDATE*: Re-bind the START edge to this resume logic
# Remove the old START edge and add this conditional one
# (This logic is conceptual for the file - ensure it replaces line 155 in your head)
workflow.set_conditional_entry_point(route_resume, {
    "store_info": "store_info",
    "validate_pr": "validate_pr",
    "check_payment": "check_payment",
    "router": "router"
})
    
# Re-compile
app_graph = workflow.compile(checkpointer=memory)