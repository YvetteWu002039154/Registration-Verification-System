# Registration Verification System

An AI-powered registration system that guides users through course selection, registration, PR card verification, and payment confirmation.

## Features

- **AI Agent**: Powered by LangChain and LangGraph to handle conversational flows.
- **Identity Verification**: Validates Canadian Permanent Resident (PR) cards.
- **Payment Verification**: Checks for payment confirmation (simulated via email/database).
- **Interactive UI**: The backend drives the frontend UI state (forms, uploads, etc.).

## Setup

1.  **Prerequisites**:
    - Python 3.9
    - `uv` (Python package manager)

2.  **Installation**:
    ```bash
    uv sync
    ```

3.  **Configuration**:
    - Ensure you have a `.env` file or environment variables set for `OPENAI_API_KEY`.

4.  **Run the Server**:
    ```bash
    uv run python src/main.py
    ```
    The server will start at `http://localhost:5050`.

## API Documentation

### 1. Chat Endpoint

**Endpoint**: `POST /api/chat`

Handles all user interactions with the AI agent.

**Request Body (JSON):**

```json
{
  "message": "User's text input",
  "session_id": "unique-session-id",
  "current_step": "OPTIONAL_STATE_TRACKER",
  "image_url": "http://localhost:5050/uploads/image.jpg"
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `message` | string | The text message from the user. |
| `session_id` | string | Unique identifier for the conversation thread. |
| `current_step` | string | (Optional) Current state of the frontend (e.g., "GREETING", "FORM"). |
| `image_url` | string | (Optional) URL of an uploaded image for the agent to analyze. |

**Response (JSON):**

```json
{
  "response": "The AI agent's text reply.",
  "session_id": "unique-session-id",
  "ui_action": "show_registration_form"
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `response` | string | The text reply from the agent. |
| `session_id` | string | The session ID (returned back). |
| `ui_action` | string | A trigger for the frontend to show a specific widget. |

**UI Actions:**

- `show_course_selector`: Display the list of available courses.
- `show_registration_form`: Display the user registration form.
- `show_upload`: Display the file upload widget (for PR cards).
- `show_payment`: Display the payment input field.
- `success_completion`: Show the success/completion screen.

### 2. File Upload Endpoint

**Endpoint**: `POST /api/upload`

Uploads a file (e.g., PR card image) to the server.

**Request (Multipart/Form-Data):**

- `file`: The file object to upload.

**Response (JSON):**

```json
{
  "url": "http://localhost:5050/uploads/unique_filename.jpg"
}
```

## Backend Tools

The AI agent utilizes several backend services to perform specific tasks. These tools are located in `src/app/tools/`.

### 1. Payment Extraction (`payment_extraction`)
Extracts payment details from Zeffy confirmation emails.

- **File**: `src/app/tools/payment_service.py`
- **Parameters**:
    - `id` (str): The unique ID of the email.
    - `subject` (str): The subject line of the email.
    - `body` (str): The full body text of the email.
- **Returns**: `dict` containing extracted payment information (e.g., amount, payer name) or an error status.

### 2. Registration Extraction (`registration_extraction`)
Processes raw registration data from the frontend form and prepares it for storage.

- **File**: `src/app/tools/registration_service.py`
- **Parameters**:
    - `data` (dict): The raw user information dictionary (must contain keys like `legalName`, `email`, `course`, etc.).
    - `pr_amount` (float): The course price for Permanent Residents.
    - `normal_amount` (float): The standard course price.
- **Returns**: `dict` containing the structured and validated registration record.

### 3. Identification Service (`identification_service`)
Validates Canadian Permanent Resident (PR) cards using OCR and visual analysis.

- **File**: `src/app/tools/document_service.py`
- **Parameters**:
    - `image_url` (str): The URL of the uploaded PR card image.
    - `register_info` (dict): User details (First Name, Last Name, PR Card Number) to cross-reference with the card.
- **Returns**: `IdentificationResult` object (or dict) containing:
    - `is_valid` (bool): Whether the card is valid.
    - `message` (str): Validation message.
    - `extracted_data` (dict): Data extracted from the card.

### 4. Reminder Service (`reminder_nonpaid_email`)
Identifies users who registered recently but have not yet completed payment.

- **File**: `src/app/tools/reminder_service.py`
- **Parameters**: None.
- **Returns**: `list[dict]` containing records of unpaid registrations from the previous day.
