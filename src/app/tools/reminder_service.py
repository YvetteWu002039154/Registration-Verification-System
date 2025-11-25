from app.utils.database_utils import get_from_csv
from app.config.config import Config

from datetime import datetime, timedelta

def reminder_nonpaid_email() -> list[dict]:
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    rows = get_from_csv(match_column=["Paid", "Created_At"], match_value=["",yesterday])
    detail = []
    try:
        for row in rows:
            email = row.get("Email")
            full_name = row.get("Full_Name")
            course = row.get("Course")
            course_date = row.get("Course_Date")
            payment_link = row.get("Payment_Link")
            support_contact = Config.CFSO_ADMIN_EMAIL_USER if row.get("PR_Status") else Config.UNIC_ADMIN_EMAIL_USER
            info = {
                "Course": course,
                "Course Date": course_date,
                "Full_name": full_name,
                "Payment Link": payment_link,
                "Support Contact": support_contact,
                "Notified": False,
                "Email": email
            }

            detail.append(info)

    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected Error happens during sending reminder email: {str(e)}"
        }

    return {"status":"success","message":"Reminder emails sent successfully","data":detail}