import re
from typing import Dict, List, Any

from app.models import IdentificationResult
from app.utils.image_utils import  local_image_to_text,get_image
from app.utils.aws_utils import AWSService
from app.utils.database_utils import update_to_csv
# ------------------------------------------------------------
# Thresholds
# ------------------------------------------------------------

PR_CARD_KEYWORD_THRESHOLD = 0.77
PR_CARD_POSITION_THRESHOLD = 0.33
PR_CARD_DRIVERS_LICENSE_THRESHOLD = 0.5

# ------------------------------------------------------------
# Keyword sets
# ------------------------------------------------------------

PR_CONF_LETTER_KEYWORDS = [
    r"\bconfirmation\s+of\s+permanent\s+residence\b",
    r"\bimm\s*(5292|5688)\b",
    r"\bclient\s*id\b",
    r"\buci\b",
]

# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------
def _relative_position_rules(normalized_results) -> float:
    """
    Calculates a confidence score based on the vertical ratio between the 
    top-most 'government' item and the bottom-most 'canada' item.
    """
    gov_items = []
    canada_boxes = []

    # 1. Collect all "government" and "canada" boxes
    for item in normalized_results:
        if re.search(r'government|gouvernement', item["text"], re.IGNORECASE):
            gov_items.append(item)
        if re.search(r'canada', item["text"], re.IGNORECASE):
            canada_boxes.append(item)

    if not gov_items or not canada_boxes:
        return 0.0

    # 2. Find the top-most government item and bottom-most canada item
    top_gov = min(gov_items, key=lambda b: b["center_y"])
    bottom_canada = max(canada_boxes, key=lambda b: b["center_x"])

    # 3. Calculate the vertical ratio
    y_span = abs(bottom_canada["center_y"] - top_gov["center_y"])
    x_span = abs(bottom_canada["center_x"] - top_gov["center_x"])

    # 4. Calculate the Aspect Ratio (Height / Width)
    aspect_ratio = y_span / x_span

    MIN_EXPECTED_RATIO  = 0.8  
    MAX_EXPECTED_RATIO = 1.2

    # 4. Check if the aspect ratio falls within the acceptable range
    if MIN_EXPECTED_RATIO <= aspect_ratio <= MAX_EXPECTED_RATIO:
        confidence = 1.0
    else:
        confidence = 0.0

    return confidence

def _keyword_in_ocr(texts) -> float:
    score = 0

    checks = {
        "gov_gouv": ["government", "gouvernement"],
        "perm_res_card": ["permanent", "resident", "card"],
        "name_label": ["name", "nom"],
        "id_label": ["id no","no id"],
        "id_number": [r"\d{2}-\d{4}-\d{4}",r"\d{4}-\d{4}"],
        "nationality_label": ["nationality","nationalité"],
        "canada": ["canada"],
        "dob": ["date of birth", "date de naissance"],
        "expiry": ["expiry", "expiration"],
    }

    for key, keywords in checks.items():
        pattern = r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"
        if any(re.search(pattern, t, re.IGNORECASE) for t in texts):
            score += 1
        
    confidence = round(score / len(checks), 2)

    return confidence

def _keyword_in_drivers_license(texts) -> float:
    score = 0

    pattern =  r"\b(" + "|".join(re.escape(k) for k in ["driver", "licence", "license", "dl"]) + r")\b"

    checks = {
        "dl_number_like": any(re.search(r"[A-Z]{1}\d{4}-\d{5}-\d{5}", t) for t in texts),
        "dl_label": any(re.search(pattern, t, re.IGNORECASE) for t in texts),
    }

    for k, v in checks.items():
        if v:
           score += 1

    confidence = round(score / len(checks), 2)

    return confidence

def _get_id_info(texts,last_name: str,first_name: str,id_number: str) -> str:
    id_pattern = id_number
    last_name_pattern = last_name.strip()
    first_name_pattern = first_name.strip()
    found_id_number = ""
    found_first_name = ""
    found_last_name = ""
    info = {}

    for t in texts:
        if found_id_number and found_first_name and found_last_name:
            break
        if re.search(id_pattern, t, re.IGNORECASE):
            found_id_number = re.search(id_pattern, t, re.IGNORECASE).group(0)
        if first_name_pattern and re.search(first_name_pattern, t, re.IGNORECASE):
            found_first_name = re.search(first_name_pattern, t, re.IGNORECASE).group(0)
        if last_name_pattern and re.search(last_name_pattern, t, re.IGNORECASE):
            found_last_name = re.search(last_name_pattern, t, re.IGNORECASE).group(0)
    info['id_number'] = found_id_number
    if not found_first_name or not found_last_name:
        info['full_name'] = ""
    else:
        info['full_name'] = f"{found_first_name} {found_last_name}".strip()
    return info

def _get_pr_card_verified_info(valid, confidence: float, details: str) -> Dict[str, Any]:
    pr_card_verified_info  = {}
    pr_card_verified_info['PR_Card_Valid'] = valid
    pr_card_verified_info['PR_Card_Valid_Confidence'] = confidence
    pr_card_verified_info['PR_Card_Details'] = details
    return pr_card_verified_info

# ------------------------------------------------------------
# Main validator
# ------------------------------------------------------------
def identification_service(image_url: str, register_info: dict) -> IdentificationResult:
    
    reasons: List[str] = []
    doc: List[str] = []
    texts = []
    valid = False
    notify_manually_check = False
    update_success = False
    keyword_confidence = 0.0
    first_name = register_info.get("First_Name", "")
    last_name = register_info.get("Last_Name", "")
    full_name = register_info.get("Full_Name", "")
    card_number = register_info.get("PR_Card_Number", "")
    phone_number = register_info.get("Phone_Number", "")
    email = register_info.get("Email", "")
    form_id = register_info.get("Form_ID", "")
    submission_id = register_info.get("Submission_ID", "")
    course = register_info.get("Course", "")
    course_date = register_info.get("Course_Date", "")

    try:
        image = get_image(source='URL', imgURL=image_url)

        local_ocr = local_image_to_text(image)
        #local_norm = normalize(local_ocr,image.shape[1], image.shape[0])

        local_texts = [item["text"] for item in local_ocr]
        local_keyword_confidence = _keyword_in_ocr(local_texts)
        #local_relative_position_confidence = _relative_position_rules(local_norm)
        local_relative_position_confidence = _relative_position_rules(local_ocr)
        local_drive_license_confidence = _keyword_in_drivers_license(local_texts)

        if local_keyword_confidence > PR_CARD_KEYWORD_THRESHOLD and \
            local_relative_position_confidence >= PR_CARD_POSITION_THRESHOLD and \
                local_drive_license_confidence < PR_CARD_DRIVERS_LICENSE_THRESHOLD:
            texts = local_texts
            keyword_confidence = local_keyword_confidence
            relative_position_confidence = local_relative_position_confidence
            drive_license_confidence = local_drive_license_confidence

        else:
            aws = AWSService()
            ocr:  List[Dict[str, Any]] = aws.extract_text_from_image(image)
            #norm: List[Dict[str, Any]] = normalize(ocr,image.shape[1], image.shape[0])

            texts = [item["text"] for item in ocr]
            keyword_confidence = _keyword_in_ocr(texts)
            drive_license_confidence = _keyword_in_drivers_license(texts)
            relative_position_confidence = _relative_position_rules(ocr)

        # ✅ PR Card
        if keyword_confidence > PR_CARD_KEYWORD_THRESHOLD:
            valid = True
            doc.append("PR_CARD")
            reasons.append(f"PR Card Check confidence is higher than the threshold.")
            # 🚫 Handwritten
            if relative_position_confidence < PR_CARD_POSITION_THRESHOLD:
                doc.append("HANDWRITTEN")
                reasons += ["Very little structured text; likely hand-written note"]
                valid = False
                notify_manually_check = True
            # 🚫 Driver’s License
            if drive_license_confidence >= PR_CARD_DRIVERS_LICENSE_THRESHOLD:
                doc = "DRIVERS_LICENSE"
                reasons += [f"Driver’s licence cues (score={drive_license_confidence})"]
                valid = False
                notify_manually_check = True
        # 🚫 Generic Photo ID
        else:
            reasons.append(f"PR Card Keyword found confidence is lower than the threshold.")
            doc.append("Generic_Photo_ID")
            valid = False

        id_info = {}
        if full_name and card_number:
            id_info = _get_id_info(texts, last_name,first_name, card_number)
            if not id_info['full_name'] or not id_info['id_number']:
                notify_manually_check = True
                reasons.append(f"Full name or ID number does not match the input.")
                valid = False
                id_info = {"full_name": full_name, "id_number": card_number}
                
        else: 
            notify_manually_check = True
            reasons.append(f"Missing full name or ID number in the registration info.")
            valid = False
        identification_result = IdentificationResult(reasons=reasons, doc_type=doc, is_valid=valid, confidence=keyword_confidence, raw_text=texts)

        card_info = _get_pr_card_verified_info(valid, keyword_confidence, reasons)
        update_success = update_to_csv(
            card_info, 
            match_column=["Full_Name","PR_Card_Number","Course","Course_Date","Paid"], 
            match_value=[full_name,card_number,course,course_date,""])

        if not update_success:
            notify_manually_check = True
            reasons.append("Failed to update the database; Maybe no or several columns are found. Manual review required.")

        if notify_manually_check:
            return {"status":"error","message":"Manual review required.",**identification_result.__dict__}
        
        return {**identification_result.__dict__, "message":"Auto verification successful.", "status":"success"}
    except Exception as e:
        reasons += [str(e)]
        identification_result = IdentificationResult(reasons=reasons, doc_type=doc, is_valid=valid, confidence=keyword_confidence, raw_text=texts)
            
        return {**identification_result.__dict__, "status": "error", "message":"Identification process failed."}
