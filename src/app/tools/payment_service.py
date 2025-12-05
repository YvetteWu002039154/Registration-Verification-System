
from app.utils.database_utils import update_to_csv, get_from_csv
from app.config.config import Config
import re
from datetime import datetime
from dateutil import parser

def payment_extraction(id, subject, body) -> dict:
    '''
    Extract Zeffy payment-related email and store it in DB.
    Args:
        id (str): Email ID to of Zeffy payment notifications.
        subject (str): Subject line of Zeffy payment notifications.
        body (str): Body of the email.
    Returns: 
       A dictionary containing payment information extracted from the email.
    '''
    notify_manually_check = False
    error_messages = []
    try:
        
        # Step 1: Extract payment information from email body
        payment_info = extract_payment_info(body)

        # Scenario 1: Could not extract payment information
        if not payment_info or not payment_info.get("Actual_Paid_Amount") or not payment_info.get("Full_Name"):
            
            return {
                "status": "error",
                "message": f"Failed to extract payment details from email with subject: {subject}"
            }
        
        # Step 2: Extract user's info from the database  

        full_name = payment_info.get("Full_Name")

        # Fetch with the payer full name and not yet marked as paid -> Never paid before
        rows = get_from_csv(
            match_column=[
                "Full_Name", 
                "Course", 
                "Course_Date",
                "Paid"
            ], 
            match_value=[
                full_name, 
                payment_info.get("Course"), 
                payment_info.get("Course_Date"), 
                ""
            ]
        )
        
        if not rows:
            # Fetch with the payer full name and marked as paid but payment status is False -> Paid before but need to correct the amount and repaid again
            rows = get_from_csv(
                match_column=[
                    "Full_Name", 
                    "Course", 
                    "Course_Date", 
                    "Paid", 
                    "Payment_Status"
                ], 
                match_value=[
                    full_name, 
                    payment_info.get("Course"), 
                    payment_info.get("Course_Date"), 
                    True,
                    False
                ]
            )

        if not rows or len(rows) != 1:

            return {
                "status": "error",
                "message": f"Failed to fetch database from email with subject: {subject}"
            }

        # Step 3: Verify the payment amount
        actual_amount = payment_info.get("Actual_Paid_Amount")
        target_amount = rows[0].get("Amount_of_Payment")

        if float(target_amount) <= actual_amount:
            payment_info['Payment_Status'] = True
        else:
            # Step 4: Notify the staff and the client when the payment amount is not correct
            payment_info['Payment_Status'] = False

        # Step 5: Update the database record
        update_success = update_to_csv(
            payment_info, 
            match_column=[
                "Full_Name", 
                "Course",
                "Course_Date", 
                "Paid"
            ], 
            match_value=[
                full_name,
                rows[0].get("Course"), 
                rows[0].get("Course_Date"), 
                ""
            ]
        ) or update_to_csv(
                payment_info,
                match_column=[
                    "Full_Name", 
                    "Course", 
                    "Course_Date", 
                    "Paid", 
                    "Payment_Status"
                ], 
                match_value=[
                    full_name, 
                    rows[0].get("Course"), 
                    rows[0].get("Course_Date"), 
                    True,
                    False
                ]
            )

        if not update_success:

           return {
                "status": "error",
                "message": f"Failed to update database from email with subject: {subject}"
            }
        
        if payment_info['Payment_Status'] is False:
            return {
                "status": "partial",
                "message": f"Payment amount {actual_amount} is less than required {target_amount} for email with subject: {subject}"
            }
        
        return {
            "status": "success",
            "message": "Payment processed successfully."
        }
    except Exception as e:
        
        return {
            "status": "error",
            "message": f"Unexpected Error happens during processing payment: {str(e)}"
        }

def extract_payment_info(email_body: str) -> dict:
    """
    Extract payment information from REAL Zeffy email format.
    
    Based on actual Zeffy template:
    - Full_Name: Participant's Name (First & Last Name) 參加者的姓名（名字和姓氏） :
    - Actual_Paid_Amount: TNew CA$125.00 payment received!
    - Course: Standard First Aid with CPR Level C & AED Certification
    - Course_Date: November 9, 2025 at 9:30 AM EST
    - Payment_Status: False (updated after amount verification)
    - Paid: True if (indicates if full name and payment amount matched)
    
    Args:
        email_body (str): The email body text
        
    Returns:
        dict: Extracted payment information with keys matching database columns
    """
    payment_info = {}
    
    # Extract payer name - Participant's Name (First & Last Name) 參加者的姓名（名字和姓氏） : hiu man suen
    name_patterns = [
        r"Participant's Name.*?:\s*(.+?)\s*I have reviewed"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, email_body, re.DOTALL)
        if match:
            # Zeffy format is "Last, First" - keep as is
            payment_info['Full_Name'] = match.group(1).strip().replace(',', '')
            break
    # Extract amount - Real Zeffy format: "Total Amount Received" or "Paid amount"
    amount_patterns = [
        r"New\s*CA\$(\d+\.\d{2})"
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, email_body, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            try:
                payment_info['Actual_Paid_Amount'] = float(amount_str)
                break
            except ValueError:
                continue
    # Extract course date - Real Zeffy format: "November 9, 2025 at 4:00 PM EST"
    date_pattern = r"\s*([A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s+[AP]M\s+[A-Z]{3})"
    match = re.search(date_pattern, email_body, re.IGNORECASE)
    if match:
        date_str = match.group(1).strip()
        try:
            # prefer dateutil (handles many TZ formats)
            parsed_date = parser.parse(date_str)
        except Exception:
            # fallback: remove trailing timezone token and parse
            no_tz = date_str.rsplit(' ', 1)[0]  # "November 16, 2025 at 9:30 AM"
            parsed_date = datetime.strptime(no_tz, "%B %d, %Y at %I:%M %p")
        payment_info['Course_Date'] = parsed_date.strftime("%Y-%m-%d")
    # Extract course name: Standard First Aid with CPR Level C & AED Certification @ UNI-Commons x CFSO
    course_pattern = r"^((?!.*New purchase).+?)\s*@ UNI-Commons x CFSO"
    match = re.search(course_pattern, email_body, re.MULTILINE)
    if match:
        payment_info['Course'] = match.group(1).strip()
    # Set payment status to True (paid) if we found key info
    if 'Full_Name' in payment_info and 'Actual_Paid_Amount' in payment_info:
        payment_info['Payment_Status'] = False  # Will be set to True after amount verification
        payment_info['Paid'] = True
        return payment_info
    else:
        return None