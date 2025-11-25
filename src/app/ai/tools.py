from langchain_core.tools import tool

from app.tools import registration_service, identification_service, payment_service, reminder_nonpaid_email
from app.models import IdentificationResult
from app.utils.database_utils import get_from_csv

# Database Simulation (Replace with your actual Supabase/SQL logic)
MOCK_DB = {
    "courses": [{"id": 1, "name": "Standard First Aid", "price": 125}, {"id": 2, "name": "Basic Life Support", "price": 80}]
}

# --- TOOL 1: Get Course Info ---
@tool()
def get_available_courses() -> list[dict]:
    """
    Retrieves the list of currently available courses and their prices.
    Use this when the user asks what classes they can register for.
    """
    # In reality: Query your database here
    return MOCK_DB["courses"]

# -- TOOL 2: Registration Info Storage ---

# --- TOOL 2: PR Card Validation (The "Vision" Tool) ---
@tool()
def store_registration_info(user_info: dict, course_id: int) -> str:
    """
    Stores the user's registration information.
    """
    # In reality: Save to your database here
    course = next((c for c in MOCK_DB["courses"] if c["id"] == course_id), None)
    if not course:
        return "Error: Course not found."
    pr_amount = course["price"]
    normal_amount = course["price"] * 1.13
    registration_data = registration_service(user_info, pr_amount=pr_amount, normal_amount=normal_amount)
    return registration_data

# --- TOOL 3: PR Card Validation (The "Vision" Tool) ---
@tool()
def validate_pr_card(image_url: str, user_info: dict) -> IdentificationResult:
    """
    Validates a Canadian Permanent Resident (PR) card from an image URL.
    Returns validation status and any detected errors (e.g., blurry, expired).
    """
    # Your logic from the old Flask /validate endpoint goes here
    # Example: Call AWS Textract or Gemini Vision API
    
    identification_data = identification_service(image_url, user_info)
    return identification_data

# --- TOOL 4: Payment Verification (The "Accountant" Tool) ---
@tool()
def check_payment_status(id,subject, body) -> dict:
    """
    Checks if a specific user has completed their Zeffy payment.
    Returns: 'PAID', 'PARTIAL', or 'UNPAID'.
    """
    # Your logic: Check Stripe/Zeffy API or local DB
    # Example logic:
    payment_result = payment_service(id,subject, body)
    return payment_result

# --- TOOL 5: Send Notification (The "Reminder" Tool) ---
@tool()
def search_nonpaid_email(email: str, course_name: str) -> list[dict]:
    """
    Sends a reminder email to the user with course details.
    """
    reminder_result = reminder_nonpaid_email()
    return reminder_result)

@tool()
def find_existing_client(client_name: str) -> str:
    """
    Searches for an existing client by name.
    """
    # Your logic to find the client in the database
    client = get_from_csv(match_column=["Full_Name"], match_value=[client_name])
    if client:
        return client
    return "Client not found."