from app.utils.extraction_tools import extract_form_id, extract_submission_id
from app.utils.database_utils import add_to_csv
from app.utils.file_utils import process_file_uploads

import re
from datetime import datetime

def _get_value_by_partial_key(data_dict, partial_key):
    """Retrieves the value when only a substring of the key is known."""
    
    for full_key, value in data_dict.items():
        if partial_key in full_key:
            return value  
            
    return None

def registration_extraction(data, pr_amount, normal_amount):
    """
    Processes the request data and returns structured information.

    Args:
        data (dict): Parsed JSON data from the request.
        pr_amount (float): Payment amount for PR status.
        normal_amount (float): Payment amount for normal status.

    Returns:
        dict: Extracted and processed data.
    """

    # Define constants for keys
    FORM_ID = "slug"
    NAME = "legalName"
    FIRST = "first"
    LAST = "last"
    EMAIL = "email"
    PHONE = "phoneNumber"
    FULL = "full"
    PAYER_NAME = "payersName"
    TYPE_OF_STATUS = "areYou"
    PR_CARD_NUMBER = "prCard"
    PR_CARD_URL = "clearFront"
    E_TRANSFER_URL = "uploadEtransfer"
    COURSE = "course"
    PAYMENTLINK = "paymentlink"

    # Extract form ID from slug
    form_id = extract_form_id(_get_value_by_partial_key(data, FORM_ID))
    # Extract personal information
    first_name = _get_value_by_partial_key(data, NAME)[FIRST]
    last_name = _get_value_by_partial_key(data, NAME)[LAST]
    full_name = f"{first_name} {last_name}"
    email = _get_value_by_partial_key(data, EMAIL)
    phone_number = _get_value_by_partial_key(data, PHONE).get(FULL)
    if _get_value_by_partial_key(data, PAYER_NAME):
        payer_full_name = f"{_get_value_by_partial_key(data, PAYER_NAME)[FIRST]} {_get_value_by_partial_key(data, PAYER_NAME)[LAST]}"
    type_of_status = _get_value_by_partial_key(data, TYPE_OF_STATUS)
    if _get_value_by_partial_key(data, COURSE):
        full_course = _get_value_by_partial_key(data, COURSE)["products"][0]["productName"]
    payment_link = _get_value_by_partial_key(data, PAYMENTLINK)
    date_pattern = r'(?:\d{4}\.)?\d{1,2}\.\d{1,2}\s*\([A-Za-z]{3}\)'
    match = re.search(date_pattern, full_course)
    if match:
        date_part = match.group(0).split('(')[0].strip()
        if date_part.count('.') == 2:
            # format YYYY.MM.DD
            course_date = datetime.strptime(date_part, '%Y.%m.%d').strftime('%Y-%m-%d')
        else:
            # format MM.DD or M.D -> prepend current year
            course_date = datetime.strptime(f"{datetime.utcnow().year}.{date_part}", '%Y.%m.%d').strftime('%Y-%m-%d')
        course = full_course[match.end():].strip()
    else:
        course_date = ""
        course = full_course.strip()
    if "Yes I am" in type_of_status:
        pr_file_upload_urls = data.get(PR_CARD_URL) \
                                if isinstance(data.get(PR_CARD_URL), list) \
                                else []
        pr_status = True
        pr_card_number = _get_value_by_partial_key(data, PR_CARD_NUMBER)
        amount_of_payment = pr_amount
    else:
        pr_status = False
        amount_of_payment = normal_amount

    registration_data = {
        'Form_ID': form_id,
        'Full_Name': full_name,
        'First_Name': first_name,
        'Last_Name': last_name,
        'Email': email,
        'Phone_Number': phone_number,
        'PR_Status': pr_status,
        'PR_Card_Number': pr_card_number if pr_status else None,
        'Amount_of_Payment': amount_of_payment,
        'PR_File_Upload_URLs': pr_file_upload_urls if pr_status else None,
        'Payer_Full_Name': payer_full_name,
        'Course': course,
        'Course_Date': course_date,
        'Payment_Link': payment_link
    }
    if E_TRANSFER_URL in data:
        e_transfer_file_upload_urls = process_file_uploads(data, E_TRANSFER_URL)
        submission_id = extract_submission_id(e_transfer_file_upload_urls)
        registration_data['E_Transfer_File_Upload_URLs'] = e_transfer_file_upload_urls
        registration_data['Submission_ID'] = submission_id
    elif registration_data["PR_Status"]:
        submission_id = extract_submission_id(pr_file_upload_urls)
        registration_data['Submission_ID'] = submission_id
    # Store extracted data into app database
    csv_data = add_to_csv(registration_data)
    if csv_data is None or csv_data is False or (hasattr(csv_data, "empty") and csv_data.empty):
        
        return {"status": "error", "message": "Failed to save registration data"}
    
    registration_data["Created_At"] = csv_data.loc[csv_data.index[0], 'Created_At']
    return {"status": "success", "message": "Registration data saved successfully", "data": registration_data}

