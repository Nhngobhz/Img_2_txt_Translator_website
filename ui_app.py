import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import uuid
from dotenv import load_dotenv
import psycopg2
import re

app = Flask(__name__)
app.secret_key = "supersecret"  # required for session
app.config['UPLOAD_FOLDER'] = "uploads"

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

load_dotenv()
gateway = os.getenv("BACKEND_API")
# Backend API endpoint

# 🔹 Postgres connection settings (CHANGE THESE for your cloud server)
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

# app.py
def save_to_postgres(image_name, translated_text):
    """Insert image name + translated text into Postgres table."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO translationstexts (file_name, response_text) VALUES (%s, %s)",
            (image_name, translated_text)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route("/", methods=["GET", "POST"])
def index():
    if "chat" not in session:
        session["chat"] = []

    if request.method == "POST":
        # 🔹 Handle Clear Chat button
        if "clear" in request.form:
            session["chat"] = []
            session.modified = True
            return redirect(url_for("index"))

        # 🔹 Handle Image Upload
        if "image" in request.files:
            file = request.files["image"]
            if file.filename != "":
                # Original filename for displaying the image
                original_filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], original_filename)
                file.save(filepath)

                # Add user message with image
                session["chat"].append({
                    "role": "user",
                    "type": "image",
                    "content": original_filename
                })

                # 🔹 Generate random filename (UUID + keep extension)
                ext = os.path.splitext(original_filename)[1]
                random_filename = f"{uuid.uuid4().hex}{ext}"

                # Call backend API with random filename
                try:
                    with open(filepath, "rb") as f:
                        files = {"file": (random_filename, f)}
                        data = {
                            "bucket_name": "nhngobhz_bucket",
                            "target_language": "en"
                        }
                        resp = requests.post(gateway, files=files, data=data)

                    if resp.ok:
                        translated_text = resp.json().get("translated_text", "No text extracted")
                        translated_text = format_translation(translated_text)
                    else:
                        translated_text = f"Error from API: {resp.text}"

                except Exception as e:
                    translated_text = f"Error calling API: {str(e)}"

                # 🔹 Save the RANDOM filename and translated text to Postgres
                save_to_postgres(random_filename, translated_text)

                # Add assistant response
                session["chat"].append({
                    "role": "assistant",
                    "type": "text",
                    "content": translated_text.splitlines()
                })

                session.modified = True
                return redirect(url_for("index"))
            
    return render_template("index.html", chat=session["chat"])



def format_translation(text: str) -> str:
    # Replace " / " with line breaks
    text = text.replace(" / ", "\n")
    
    # Add a newline after numbered items like "1." or "2."
    text = re.sub(r"(\d+\.\s)", r"\n\1", text)

    # Add spacing around sections (before "**English Translation:**")
    text = text.replace("**English Translation:**", "\n\n**English Translation:**\n")
    text = text.replace("**Extracted Japanese Text:**", "\n\n**Extracted Japanese Text:**\n")
    
    return text.strip()



if __name__ == "__main__":
    app.run(port=5001, debug=True)