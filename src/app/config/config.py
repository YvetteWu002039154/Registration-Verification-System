import json
import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

class Config:
    """
    App configuration loaded from environment variables.

    Required:
      - AWS_ACCESS_KEY
      - AWS_SECRET_KEY
      - S3_BUCKET_NAME: name of the S3 bucket

      - ADMIN_EMAIL_USER: admin email address to use for sending notifications
      - ADMIN_EMAIL_PASSWORD: admin email password

      - ERROR_NOTIFICATION_EMAIL: email address to send error notifications to

      - GOOGLE_SPREADSHEET_ID: ID of the Google Spreadsheet to use
      - GOOGLE_WORKSHEET_NAME: Name of the worksheet within the spreadsheet
    Optional:
      (only set then checking Zeffy payment notification emails in this mailbox)
      - CFSO_ADMIN_EMAIL_USER: CFSO admin email address for IMAP access
      - CFSO_ADMIN_EMAIL_PASSWORD: CFSO admin email password for IMAP access
      - UNIC_ADMIN_EMAIL_USER: UNIC admin email address for IMAP access
      - UNIC_ADMIN_EMAIL_PASSWORD: UNIC admin email password for IMAP access

      (defaults)
      - FLASK_HOST: host to run the Flask app on (default: 0.0.0.0)
      - FLASK_PORT: port to run the Flask app on (default: 5000)
      - FLASK_DEBUG: enable/disable debug mode (default: true)
      - REGION_NAME: AWS region (default: us-east-1)

      (only required if using JotForm image URLs)
      - JOTFORM_API_KEY: API key for JotForm

    Copy .env.example -> .env and fill the required values.
    """
    # Flask
    FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'

    # AWS 
    AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
    AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
    REGION_NAME = os.getenv('REGION_NAME', 'us-east-1')

    # Admin email credentials, used for IMAP access and sending out notifications
    CFSO_ADMIN_EMAIL_PASSWORD = os.getenv('CFSO_ADMIN_EMAIL_PASSWORD')
    CFSO_ADMIN_EMAIL_USER = os.getenv('CFSO_ADMIN_EMAIL_USER')
    UNIC_ADMIN_EMAIL_PASSWORD = os.getenv('UNIC_ADMIN_EMAIL_PASSWORD')
    UNIC_ADMIN_EMAIL_USER = os.getenv('UNIC_ADMIN_EMAIL_USER')
    ADMIN_EMAIL_USER = os.getenv('ADMIN_EMAIL_USER')
    ADMIN_EMAIL_PASSWORD = os.getenv('ADMIN_EMAIL_PASSWORD')

    # Flask-Mail configuration (The mail showing as sender)
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME =  os.getenv('SENDER_EMAIL_USER',ADMIN_EMAIL_USER)
    MAIL_PASSWORD = os.getenv('SENDER_EMAIL_PASSWORD',ADMIN_EMAIL_PASSWORD)
    MAIL_DEFAULT_SENDER = os.getenv('SENDER_EMAIL_USER',ADMIN_EMAIL_USER)

    # Error notification email recipient
    NOTIFICATION_RECIPIENTS = os.getenv('ERROR_NOTIFICATION_EMAIL', ADMIN_EMAIL_USER)
    ERROR_NOTIFICATION_EMAIL = []

    if NOTIFICATION_RECIPIENTS:
      try:
          parsed_list = json.loads(NOTIFICATION_RECIPIENTS)

          if isinstance(parsed_list, list):
              ERROR_NOTIFICATION_EMAIL = parsed_list
          else:
              ERROR_NOTIFICATION_EMAIL = [parsed_list]

      except json.JSONDecodeError:
          ERROR_NOTIFICATION_EMAIL = [NOTIFICATION_RECIPIENTS]

    # Jotform
    JOTFORM_API_KEY = os.getenv('JOTFORM_API_KEY')


    # Google Sheets
    GOOGLE_SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID')
    GOOGLE_WORKSHEET_NAME = os.getenv('GOOGLE_WORKSHEET_NAME')

   # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')