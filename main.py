from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
import msal
import os
import base64
import hashlib
import secrets

app = FastAPI()

# Microsoft Azure AD Configuration
CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "4bfb95dc-d50c-47a5-bc82-c1899c60a199")
CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "WuK8Q~ePCKu36xjd-..XcLb-AbgHW~DZMt8IcbsZ")
TENANT_ID = os.getenv("OAUTH_TENANT_ID", "3d7a3f90-1d2c-4d91-9b49-52e098cf9eb8")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = "/auth/callback/2Rv37eu9QWC"
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
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        redirect_uri=f"http://localhost:8000{REDIRECT_PATH}",
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
    
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=f"http://localhost:8001{REDIRECT_PATH}",  # Changed to 8001
        code_verifier=code_verifier
    )
    if "access_token" in result:
        return RedirectResponse(url="http://localhost:8000")  # Redirect to Chainlit server
    return {"error": "Authentication failed"}

@app.get("/chainlit")
async def chainlit():
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=http://localhost:8000/">')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8001)