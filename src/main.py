from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import uuid
import os
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
    session_id = data.get('session_id')
    image_url = data.get('image_url', None) # Optional image from frontend

    # Generate a session ID if one doesn't exist (for new users)
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        # --- CALL THE AI AGENT ---
        ai_response = process_message(user_message, session_id, image_url)
        
        # Check for UI Triggers (e.g., if agent wants to show a form)
        ui_action = "text"
        if "[FORM_TRIGGER]" in ai_response:
            ui_action = "show_registration_form"
            ai_response = ai_response.replace("[FORM_TRIGGER]", "")

        return jsonify({
            "response": ai_response,
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
