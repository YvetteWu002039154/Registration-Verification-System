from typing import Annotated, TypedDict, List, Literal
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from app.config import Config

# Import AI tools
from app.ai.tools import (
    get_available_courses,
    store_registration_info,
    validate_pr_card,
    check_payment_status,
    search_nonpaid_email,
    find_existing_client
)

# --- 1. Define the State ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

# --- 2. Setup LLM & Tools ---
tools = [
    get_available_courses,
    store_registration_info,
    validate_pr_card,
    check_payment_status,
    search_nonpaid_email,
    find_existing_client
]

llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=Config.OPENAI_API_KEY)
llm_with_tools = llm.bind_tools(tools)

# --- 3. Define Nodes ---

def greeting_node(state: AgentState):
    """
    Entry node. Checks if we should greet or pass to agent.
    """
    # In this simplified flow, we just pass through. 
    # The system prompt in the agent node handles the persona.
    return {}

def agent_node(state: AgentState):
    """
    The Brain. Decides to call tools or respond.
    """
    messages = state["messages"]
    
    # System Prompt to guide the agent and UI tags
    system_prompt = SystemMessage(content="""
        You are a helpful Registration Assistant for a course system.
        Your goal is to help users register for courses, validate their identity (PR card), and confirm payment.

        You have access to tools. Use them when appropriate.

        **UI Triggers:**
        You must include specific tags in your response when you want the user to see a specific UI widget.
        - If the user asks about courses or you list them, include `[SHOW_COURSE_SELECTOR]` at the end.
        - If the user selects a course, ask if they are a Permanent Resident (PR).
        - If they are a PR, ask them to upload their PR card FIRST and include `[SHOW_UPLOAD]`.
        - Once you have the PR card (or if they are not a PR), ask them to fill out the registration details and include `[SHOW_REGISTRATION_FORM]`.
        - When you receive the registration details (and have the PR card URL if applicable), call `store_registration_info`. Ensure you include the PR card URL in the `clearFront` field of the user_info if they are a PR.
        - If storage is successful, ask for payment and include `[SHOW_PAYMENT]`.
        - If the user confirms payment and you verify it, congratulate them and include `[SUCCESS_COMPLETION]`.

        **Flow:**
        1. Greet the user if they say hi.
        2. Guide them through: Course Selection -> Check PR Status -> PR Upload (if PR) -> Registration Form -> Store Info -> Payment -> Success.
        3. Always be polite.
    """)
            
    # We prepend the system prompt to the messages list for the invocation
    # This ensures the model sees it every time without adding it to the history permanently if we don't want to.
    # However, LangGraph add_messages handles history. Let's just pass it in the invoke call.
    response = llm_with_tools.invoke([system_prompt] + messages)
    
    # --- LOGGING ---
    print("\n--- 🤖 Agent Decision ---")
    if response.tool_calls:
        print(f"Tool Calls: {response.tool_calls}")
    print("-------------------------\n")
    # ---------------

    return {"messages": [response]}

def tools_node(state: AgentState):
    """
    Executes tools.
    """
  
    result = ToolNode(tools).invoke(state)

    return result

# --- 4. Build the Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("greeting", greeting_node)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)

# Edges
workflow.add_edge(START, "greeting")
workflow.add_edge("greeting", "agent")

def should_continue(state: AgentState) -> Literal["tools", END]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "tools"
    return END

workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

# Compile
memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory)

# --- 5. Process Message Function ---
def process_message(user_input: str, thread_id: str, image_url: str = None, original_image_url: str = None):
    config = {"configurable": {"thread_id": thread_id}}
    
    # Construct input message
    content = []
    if user_input:
        content.append({"type": "text", "text": user_input})
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
        # Also add a text hint so the agent knows an image was uploaded
        hint_text = " (User uploaded an image)."
        if original_image_url:
            hint_text += f" The URL for this image is: {original_image_url}. Use this URL when calling tools."
        content.append({"type": "text", "text": hint_text})
        
    human_msg = HumanMessage(content=content)
    
    # Run the graph
    # We use invoke to run until the graph stops (at END)
    result = app_graph.invoke({"messages": [human_msg]}, config=config)
    
    # Extract the last message content
    last_msg = result["messages"][-1]
    final_response = ""
    if isinstance(last_msg, AIMessage):
        final_response = last_msg.content
    
    return final_response