import os
import uuid
from flask import Blueprint, redirect, request, session, url_for, current_app, render_template_string
import msal
import requests
from urllib.parse import urljoin

auth_bp = Blueprint("auth", __name__, url_prefix="/auth") # Blueprint prefix is /auth

# SCOPES: MSAL Python adds , profile, offline_access by default.
# We only need to specify additional resource scopes like User.Read and 'email'.
SCOPES = ["User.Read", "email"]


def _get_msal_app_config():
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    authority = os.getenv("AUTHORITY")
    
    if not all([client_id, client_secret, authority]):
        current_app.logger.error("MSAL config (CLIENT_ID, CLIENT_SECRET, AUTHORITY) missing in .env")
        return None, None, None
    return client_id, client_secret, authority

def _build_msal_app(cache=None):
    client_id, client_secret, authority = _get_msal_app_config()
    if not client_id:
        return None
        
    return msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
        token_cache=cache
    )

def _get_redirect_uri():
    app_base_url = os.getenv("APP_BASE_URL", "http://localhost:5001")
    # REDIRECT_CALLBACK_SEGMENT is just the final part, e.g., "getAToken"
    redirect_callback_segment = os.getenv("REDIRECT_CALLBACK_SEGMENT", "getAToken").lstrip("/")
    # The full path includes the blueprint prefix
    full_redirect_path = f"{auth_bp.url_prefix}/{redirect_callback_segment}" 
    return urljoin(app_base_url, full_redirect_path)

@auth_bp.route("/login")
def login():
    whatsapp_id = request.args.get("whatsapp_id")
    if not whatsapp_id:
        return "Error: whatsapp_id parameter is missing.", 400
    
    session["whatsapp_id"] = whatsapp_id
    session["state"] = str(uuid.uuid4())
    
    msal_app = _build_msal_app()
    if not msal_app:
        return "Error: MSAL app init failed (config missing).", 500

    redirect_uri = _get_redirect_uri()
    current_app.logger.info(f"Generated redirect_uri for login: {redirect_uri}")

    auth_url = msal_app.get_authorization_request_url(
        SCOPES,
        state=session["state"],
        redirect_uri=redirect_uri
    )
    return redirect(auth_url)

# The route path is now just the segment, as it's relative to the blueprint's url_prefix
@auth_bp.route(f"/{os.getenv('REDIRECT_CALLBACK_SEGMENT', 'getAToken').lstrip('/')}")
def authorized():
    if request.args.get("state") != session.get("state"):
        return "Error: State mismatch. CSRF?", 400
    
    if "error" in request.args:
        return f"Login failed: {request.args.get('error')} - {request.args.get('error_description')}", 400

    code = request.args.get("code")
    if not code:
        return "Error: Auth code not in callback.", 400

    msal_app = _build_msal_app()
    if not msal_app:
        return "Error: MSAL app init failed (config missing).", 500

    redirect_uri = _get_redirect_uri()
    current_app.logger.info(f"Using redirect_uri for token acquisition: {redirect_uri}")

    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    if "error" in result:
        current_app.logger.error(f"Token acquisition error: {result}")
        return f"Error acquiring token: {result.get('error_description', 'Unknown')}", 500

    user_id_from_token = result.get("id_token_claims", {}).get("oid") 
    if not user_id_from_token:
        user_id_from_token = result.get("id_token_claims", {}).get("sub")
    
    if not user_id_from_token:
        current_app.logger.error(f"Could not get user ID from token: {result.get('id_token_claims')}")
        return "Error: Could not ID user from token.", 500

    whatsapp_id = session.pop("whatsapp_id", None)
    session.pop("state", None)

    if not whatsapp_id:
        current_app.logger.error("Critical: whatsapp_id missing post-auth.")
        return "Error: whatsapp_id missing in session.", 500

    session["user"] = result.get("id_token_claims")

    webhook_payload = {
        "whatsapp_id": whatsapp_id,
        "microsoft_user_id": user_id_from_token,
        "name": result.get("id_token_claims", {}).get("name"),
        "email": result.get("id_token_claims", {}).get("preferred_username")
    }
    
    webhook_url_env = os.getenv("WEBHOOK_URL")
    webhook_status = "Webhook not attempted (URL not configured)."
    
    if webhook_url_env:
        try:
            current_app.logger.info(f"Sending to webhook: {webhook_url_env} payload: {webhook_payload}")
            response = requests.post(webhook_url_env, json=webhook_payload, timeout=10)
            response.raise_for_status()
            webhook_status = f"Webhook notified (Status: {response.status_code})."
            current_app.logger.info(webhook_status)
        except requests.exceptions.RequestException as e:
            webhook_status = f"Error notifying webhook: {e}"
            current_app.logger.error(webhook_status)
    else:
        current_app.logger.warning(webhook_status)
    success_message_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login efetuado com sucesso</title>
            <meta http-equiv="refresh" content="3;url=whatsapp://send?phone={whatsapp_id}&text=Login%20realizado%20com%20sucesso!" />
            <script type="text/javascript">
                // Tenta redirecionar para o WhatsApp após 2 segundos
                setTimeout(function()  {{
                    window.location.href = "whatsapp://send?phone={whatsapp_id}&text=Login%20realizado%20com%20sucesso!";
                }}, 2000);
            </script>
        </head>
        <body>
            <h1>Login realizado com sucesso!</h1>
            <p>Hello {result.get('id_token_claims', {}).get('name', 'User')}.</p>
            <p>Redirecionando para o WhatsApp em 3 segundos...</p>
            <p>Se o redirecionamento não funcionar, <a href="whatsapp://send?phone=SEU_NUMERO_WHATSAPP">clique aqui para voltar ao WhatsApp</a>.</p>
            <hr>
            <p><small>Webhook Status: {webhook_status}</small></p>
        </body>
        </html>
    """
        

    # success_message_html = f"""
    # <!DOCTYPE html><html><head><title>Login Successful</title></head><body>
    #     <h1>Login Successful!</h1>
    #     <p>Hello {result.get('id_token_claims', {}).get('name', 'User')}.</p>
    #     <p>WhatsApp ID: {whatsapp_id}</p>
    #     <p>Microsoft User ID: {user_id_from_token}</p>
    #     <p>Email: {result.get('id_token_claims', {}).get('preferred_username', 'N/A')}</p>
    #     <p>You can now return to WhatsApp.</p><hr>
    #     <p>Webhook Status: {webhook_status}</p>
    #     <p><small>Data sent: {webhook_payload if webhook_url_env else 'N/A (WEBHOOK_URL not set)'}</small></p>
    # </body></html>
    # """
    return render_template_string(success_message_html)

@auth_bp.route("/logout")
def logout():
    session.clear()
    app_base_url = os.getenv("APP_BASE_URL", "http://localhost:5001")
    authority = os.getenv("AUTHORITY")
    
    # This will redirect to the app's static logged_out_message.html after Microsoft logout.
    # The path for url_for should be relative to the main app, not the blueprint for static files.
    post_logout_uri = urljoin(app_base_url, url_for("serve_static_files", path="logged_out_message.html"))
    
    if authority:
        logout_url = f"{authority}/oauth2/v2.0/logout?post_logout_redirect_uri={post_logout_uri}"
        return redirect(logout_url)
    else:
        return redirect(post_logout_uri)