from langchain_core.tools import tool

from app.tools import registration_extraction, identification_service, payment_extraction, reminder_nonpaid_email
from app.utils.database_utils import get_from_csv

# Database Simulation (Replace with your actual Supabase/SQL logic)
MOCK_DB = {
    "courses": [
        {"id": "sfa", "name": "2025.12.05 (Fri) Standard First Aid", "price": 125, "description": "Learn how to perform CPR and First Aid","payment_link": "https://www.zeffy.com/ticketing/standard-first-aid-with-cpr-level-c-and-aed-certification-uni-commons-x-cfso"},
        {"id": "mft", "name": "2025.07.06 (Sat) Mask Fit Testing", "price": 80, "description": "Learn how to perform CPR and First Aid","payment_link":"https://www.zeffy.com/ticketing/red-cross-standard-cpr-aed-level-c--20250706"},
        {"id": "bjj", "name": "2025.08.15 (Fri) Brazilian Jiu-Jitsu Training", "price": 100, "description": "Brazilian Jiu-Jitsu Training","payment_link":"https://www.zeffy.com/ticketing/brazilian-jiu-jitsu-training-courses-pr"},
        {"id": "fhc", "name": "2025.09.10 (Wed) Food Handler Certification", "price": 90, "description": "Food Handler Certification","payment_link":"https://www.zeffy.com/ticketing/food-handler-certification-course"},
    ]
}

# --- TOOL 1: Get Course Info ---
@tool()
def get_available_courses() -> list[dict]:
    """
    Retrieves the list of currently available courses and their prices.
    Use this when the user asks what classes they can register for.
    
    Returns:
        list[dict]: A list of dictionaries, each containing 'id', 'name', and 'price' of a course.
    """
    # In reality: Query your database here
    return MOCK_DB["courses"]

# --- TOOL 2: Registration Info Storage ---
@tool()
def store_registration_info(user_info: dict, course_id: str) -> dict:
    """
    Stores the user's registration information in the database.
    
    Args:
        user_info (dict): A dictionary containing user details. 
                          MUST follow this structure to match the backend extraction logic:
                          {
                              "legalName": {"first": "John", "last": "Doe"},
                              "payersName": {"first": "John", "last": "Doe"},
                              "email": "john@example.com",
                              "phoneNumber": {"full": "555-1234"},
                              "areYou": "Yes I am a PR" (or "No"),
                              "prCard": "12345678" (if PR),
                              "clearFront": ["url1"] (if PR)
                          }
        course_id (str): The ID of the course (e.g., 'sfa').
        
    Returns:
        dict: A dictionary with the status of the operation and the stored data.
    """
    course = next((c for c in MOCK_DB["courses"] if c["id"] == course_id), None)
    if not course:
        return {"status": "error", "message": "Course not found."}
    pr_amount = course["price"]
    normal_amount = course["price"] * 1.13
    
    from datetime import datetime
    user_info["slug"] = f"/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    user_info["course"] = {
        "products": [{
            "productName": f"{course['name']}"
        }]
    }
    user_info["paymentlink"] = course["payment_link"]
    # registration_service expects 'data' (the user_info dict) and amounts
    registration_data = registration_extraction(user_info, pr_amount=pr_amount, normal_amount=normal_amount)
    return registration_data

# --- TOOL 3: PR Card Validation (The "Vision" Tool) ---
@tool()
def validate_pr_card(image_url: str, user_info: dict) -> dict:
    """
    Validates a Canadian Permanent Resident (PR) card from an image URL.
    
    Args:
        image_url (str): The URL of the uploaded PR card image.
        user_info (dict): The user's registration info to match against the card (must contain 'First_Name', 'Last_Name', 'PR_Card_Number').
        
    Returns:
        dict: Validation results containing 'is_valid' (bool), 'message' (str), and 'extracted_data' (dict).
    """
    # identification_service returns an IdentificationResult object or dict
    identification_data = identification_service(image_url, user_info)
    
    # Ensure we return a dict for the LLM
    if hasattr(identification_data, "dict"):
        return identification_data.dict()
    return identification_data

# --- TOOL 4: Payment Verification (The "Accountant" Tool) ---
@tool()
def check_payment_status(email_id: str, subject: str, body: str) -> dict:
    """
    Checks if a specific user has completed their Zeffy payment by analyzing a payment confirmation email.
    
    Args:
        email_id (str): The unique ID of the email.
        subject (str): The subject line of the email.
        body (str): The full body text of the email.
        
    Returns:
        dict: A dictionary with 'status' ('success', 'partial', 'error') and a 'message'.
    """
    # Note: The underlying service function is named 'payment_extraction' in some contexts, 
    # but imported as 'payment_service' in this file.
    payment_result = payment_extraction(email_id, subject, body)
    return payment_result

# --- TOOL 5: Send Notification (The "Reminder" Tool) ---
@tool()
def search_nonpaid_email() -> list[dict]:
    """
    Searches for records of users who registered yesterday but have not yet paid.
    
    Returns:
        list[dict]: A list of unpaid registration records.
    """
    # The underlying function doesn't take arguments based on the previous code
    reminder_result = reminder_nonpaid_email()
    return reminder_result

@tool()
def find_existing_client(client_name: str) -> list[dict] | str: # Need to change it to use pr card number incase sensitive info leak, like using name to get pr card number
    """
    Searches for an existing client by their full name in the database.
    
    Args:
        client_name (str): The full name of the client to search for.
        
    Returns:
        list[dict] | str: A list of matching client records if found, otherwise a "Client not found" message.
    """
    # Your logic to find the client in the database
    clients = get_from_csv(match_column=["Full_Name"], match_value=[client_name])
    if clients:
        return clients
    return "Client not found."