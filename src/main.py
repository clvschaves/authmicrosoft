import os
import sys
from dotenv import load_dotenv
load_dotenv()

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

#load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")) # Load .env file from project root

from flask import Flask, send_from_directory, render_template_string
# from src.models.user import db # Database not used in this auth-only app
# from src.routes.user import user_bp # Default user routes not used
from src.routes.auth_routes import auth_bp # Import our auth blueprint

# # Configuração do Redis
# redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
# redis_client = redis.from_url(redis_url, ssl_cert_reqs=None)


app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))
# Load SECRET_KEY from environment variable, with a default for safety (though user should set a strong one)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_default_secret_key_please_change")
# app.config["SESSION_TYPE"] = "redis"
# app.config["SESSION_REDIS"] = redis_client
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 1200  # 20 minutos em segundos
#app.config["SESSION_USE_SIGNER"] = True
#app.config["SESSION_KEY_PREFIX"] = "flask_session:"


# Initialize gerenciador de sessão
#Session(app)

# Dicionário para mapear os IDs do WhatsApp para os IDs do Microsoft
microsoft_session_map = {}

# Register the authentication blueprint
app.register_blueprint(auth_bp, url_prefix="/auth")

# Database setup is commented out as it's not strictly needed for this auth flow
# app.config["SQLALCHEMY_DATABASE_URI"] = f"mysql+pymysql://{os.getenv("DB_USERNAME", "root")}:{os.getenv("DB_PASSWORD", "password")}@{os.getenv("DB_HOST", "localhost")}:{os.getenv("DB_PORT", "3306")}/{os.getenv("DB_NAME", "mydb")}"
# app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# db.init_app(app)
# with app.app_context():
#     db.create_all()

# Função simplificada para "invalidar" sessões
def invalidate_session_by_whatsapp_id(whatsapp_id):
    if whatsapp_id in whatsapp_session_map:
        whatsapp_session_map.pop(whatsapp_id, None)
        return True
    return False

# def invalidate_session_by_whatsapp_id(whatsapp_id):
#     """
#     Invalidate the session for the given WhatsApp ID.
#     """
#     if whatsapp_id in microsoft_session_map:
#         session_id = microsoft_session_map[whatsapp_id]
#         #remover a sessão do Redis
#         redis_client.delete(f"flask_session:{session_id}")
#         #remover o mapeamento
#         whatsapp_session_map.pop(whatsapp_id, None) 
#     return False

@app.route("/")
@app.route("/index.html")
def serve_index_or_static():
    # This will serve index.html from the static folder by default
    # or specific files if path is given and exists.
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    index_path = os.path.join(static_folder_path, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(static_folder_path, "index.html")
    else:
        # Fallback if no index.html, provide a simple welcome page with login link
        # The whatsapp_id would typically be appended by the system sending the link
        welcome_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Welcome</title></head>
        <body>
            <h1>Authentication App</h1>
            <p>To login, you would typically receive a link like: 
            <a href="/auth/login?whatsapp_id=YOUR_WHATSAPP_ID_HERE">/auth/login?whatsapp_id=YOUR_WHATSAPP_ID_HERE</a>
            </p>
            <p>Replace YOUR_WHATSAPP_ID_HERE with the actual ID.</p>
        </body>
        </html>
        """
        return render_template_string(welcome_html)

@app.route("/<path:path>")
def serve_static_files(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404
    
    file_path = os.path.join(static_folder_path, path)
    if os.path.exists(file_path):
        return send_from_directory(static_folder_path, path)
    else:
        # If specific file not found, try to serve index.html (e.g. for SPA routing)
        index_path = os.path.join(static_folder_path, "index.html")
        if os.path.exists(index_path):
             return send_from_directory(static_folder_path, "index.html")
        return "File not found", 404

if __name__ == "__main__":
    # Make sure to create a .env file with your actual credentials and settings
    # based on .env.example before running for real.
    if not os.getenv("CLIENT_ID") or not os.getenv("CLIENT_SECRET") or not os.getenv("AUTHORITY"):
        print("WARNING: CLIENT_ID, CLIENT_SECRET, or AUTHORITY environment variables are not set.")
        print("Please create a .env file based on .env.example and populate these values.")
    app.run(host="0.0.0.0", port=5001, debug=os.getenv("FLASK_DEBUG", "True").lower() == "true")

