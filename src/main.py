from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import uuid
import os
import base64
from werkzeug.utils import secure_filename

# Import the agent logic we just wrote
from app.ai.agent import process_message
from app.config import Config

app = Flask(__name__)
CORS(app)

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    data = request.json
    user_message = data.get('message', '')
    current_step = data.get('current_step', None)
    session_id = data.get('session_id')
    image_url = data.get('image_url', None) # Optional image from frontend

    # Generate a session ID if one doesn't exist (for new users)
    if not session_id:
        session_id = str(uuid.uuid4())

    original_image_url = image_url

    # Convert local image URLs to Base64 so OpenAI can access them
    if image_url and ("localhost" in image_url or "127.0.0.1" in image_url) and "uploads/" in image_url:
        try:
            filename = image_url.split("uploads/")[-1]
            # Resolve path relative to this file
            uploads_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))
            file_path = os.path.join(uploads_path, filename)
            
            if os.path.exists(file_path):
                with open(file_path, "rb") as img_file:
                    b64_str = base64.b64encode(img_file.read()).decode('utf-8')
                    # Determine extension
                    ext = os.path.splitext(filename)[1].lower().replace('.', '')
                    if ext == 'jpg': ext = 'jpeg'
                    # Update image_url to data URI
                    image_url = f"data:image/{ext};base64,{b64_str}"
        except Exception as e:
            print(f"Warning: Could not convert local image to Base64: {e}")

    try:
        # --- CALL THE AI AGENT ---
        # Pass current_step if your agent uses it, otherwise just message/session/image
        ai_response = process_message(user_message, session_id, image_url, original_image_url)
        
        # Check for UI Triggers based on tags in the response
        ui_action = None
        
        if "[SHOW_COURSE_SELECTOR]" in ai_response:
            ui_action = "show_course_selector"
            ai_response = ai_response.replace("[SHOW_COURSE_SELECTOR]", "")
        elif "[SHOW_REGISTRATION_FORM]" in ai_response:
            ui_action = "show_registration_form"
            ai_response = ai_response.replace("[SHOW_REGISTRATION_FORM]", "")
        elif "[SHOW_UPLOAD]" in ai_response:
            ui_action = "show_upload"
            ai_response = ai_response.replace("[SHOW_UPLOAD]", "")
        elif "[SHOW_PAYMENT]" in ai_response:
            ui_action = "show_payment"
            ai_response = ai_response.replace("[SHOW_PAYMENT]", "")
        elif "[SUCCESS_COMPLETION]" in ai_response:
            ui_action = "success_completion"
            ai_response = ai_response.replace("[SUCCESS_COMPLETION]", "")

        return jsonify({
            "response": ai_response.strip(),
            "session_id": session_id,
            "ui_action": ui_action
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Something went wrong"}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """
    Simple endpoint to save an image and return a URL/Path.
    In production, upload this to S3/Supabase Storage.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Restrict to common image extensions
    ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_EXT:
        return jsonify({"error": "Unsupported file type"}), 400

    # Ensure uploads dir exists
    uploads_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    uploads_dir = os.path.abspath(uploads_dir)
    os.makedirs(uploads_dir, exist_ok=True)

    # Generate unique filename to avoid collisions
    unique_name = f"{uuid.uuid4().hex}{ext.lower()}"
    save_path = os.path.join(uploads_dir, unique_name)
    file.save(save_path)

    # Build a URL for the saved file (served by the /uploads/<filename> route)
    # Use request.host_url which includes scheme and host:port
    file_url = request.host_url.rstrip('/') + f"/uploads/{unique_name}"
    return jsonify({"url": file_url})


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files from the uploads directory."""
    uploads_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    uploads_dir = os.path.abspath(uploads_dir)
    return send_from_directory(uploads_dir, filename)

if __name__ == '__main__':
    app.run(debug=Config.FLASK_DEBUG, port=Config.FLASK_PORT)
