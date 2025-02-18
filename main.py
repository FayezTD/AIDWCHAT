from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
import msal
import os
import base64
import hashlib
import secrets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Microsoft Azure AD Configuration
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = os.getenv("REDIRECT_PATH")
if REDIRECT_PATH is None:
    raise ValueError("REDIRECT_PATH environment variable is not set")
SCOPE = ["User.Read"]
SESSION = {}

# Initialize MSAL application
msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET
)

def generate_pkce_pair():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

@app.get("/")
async def root():
    code_verifier, code_challenge = generate_pkce_pair()
    SESSION['code_verifier'] = code_verifier
    redirect_uri = f"https://aidw-assistant-dmdjargjhvh3dqez.eastus2-01.azurewebsites.net{REDIRECT_PATH}" if os.getenv("ENV") == "production" else f"http://localhost:8000{REDIRECT_PATH}"
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method='S256'
    )
    return RedirectResponse(url=auth_url)

@app.get(REDIRECT_PATH)
async def authorized(request: Request):
    code = request.query_params.get('code')
    code_verifier = SESSION.pop('code_verifier', None)
    if not code_verifier:
        return {"error": "Code verifier not found in session."}
    
    redirect_uri = f"https://aidw-assistant-dmdjargjhvh3dqez.eastus2-01.azurewebsites.net{REDIRECT_PATH}" if os.getenv("ENV") == "production" else f"http://localhost:8001{REDIRECT_PATH}"
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier
    )
    if "access_token" in result:
        SESSION['user_email'] = result.get('id_token_claims', {}).get('preferred_username', 'Unknown')
        return RedirectResponse(url="https://aidw-assistant-dmdjargjhvh3dqez.eastus2-01.azurewebsites.net" if os.getenv("ENV") == "production" else "http://localhost:8000")
    return {"error": "Authentication failed"}

@app.get("/chainlit")
async def chainlit():
    user_email = SESSION.get('user_email', 'Unknown')
    return HTMLResponse(f'<meta http-equiv="refresh" content="0;url=https://aidw-assistant-dmdjargjhvh3dqez.eastus2-01.azurewebsites.net/" if os.getenv("ENV") == "production" else "http://localhost:8000/">')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0" if os.getenv("ENV") == "production" else "localhost", port=8001)