import urllib.request
import json
import os
import ssl
import logging
import asyncio
from typing import Dict, Any, List, Optional
import chainlit as cl
import re
from datetime import datetime
from dotenv import load_dotenv
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import io
import base64
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
import msal
import secrets
import hashlib
from dataclasses import dataclass
from typing import Dict, Optional

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'chatbot_{datetime.now().strftime("%Y%m%d")}.log')
    ]
)
logger = logging.getLogger(__name__)

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

STARTER_QUESTIONS = [
    {
        "title": "🌍 Potential market size of AB InBev Operation",
        "question": "How many countries does AB InBev operate in, and what is the potential market size for the ConnectAI solution in these regions?"
    },
    {
        "title": "💰 Annual cost savings for PepsiCo",
        "question": "What is the anticipated annual cost savings for PepsiCo by optimizing costs through shared resources and standardized practices with the PepGenX platform?"
    },
    {
        "title": "📈 Monthly ACR for AI services at ABN AMRO",
        "question": "How much has the monthly ACR for AI services contributed to the overall operational efficiency of the ECM department at ABN AMRO?"
    },
    {
        "title": "📝 Complaints letter processing time",
        "question": "How many minutes does it now take to produce a complaints letter after the integration of Azure OpenAI, compared to the previous time?"
    },
    {
        "title": "🔄 Azure OpenAI Integration Benefits",
        "question": "How does the integration of Azure OpenAI with Logic Apps and Cosmos DB enhance the marketing capabilities of AB InBev?"
    },
    {
        "title": "🔄 Bajaj vs Starbucks AIDW Implementation",
        "question": "Please compare how Bajaj and Starbucks use the AIDW to enhance their business, cite both the documents"
    }
]

class DataVisualizationHandler:
    @staticmethod
    def process_chart(chart_data: str) -> str:
        try:
            data = json.loads(chart_data)
            chart_elements = [
                "```mermaid",
                "pie",
                f"title {data.get('title', 'Chart')}"
            ]
            for item in data.get('data', []):
                chart_elements.append(f'    "{item["label"]}" : {item["value"]}')
            chart_elements.append("```")
            return '\n'.join(chart_elements)
        except Exception as e:
            logger.error(f"Chart generation error: {str(e)}")
            return f"<!-- Error generating chart: {str(e)} -->"

    @staticmethod
    def process_table(table_data: str) -> str:
        try:
            data = json.loads(table_data)
            table_elements = ['| ' + ' | '.join(data.get('headers', [])) + ' |']
            table_elements.append('| ' + ' | '.join(['---'] * len(data.get('headers', []))) + ' |')
            for row in data.get('rows', []):
                table_elements.append('| ' + ' | '.join(map(str, row)) + ' |')
            return '\n'.join(table_elements)
        except Exception as e:
            logger.error(f"Table generation error: {str(e)}")
            return f"<!-- Error generating table: {str(e)} -->"

    @staticmethod
    def process_flowchart(flow_data: str) -> str:
        try:
            data = json.loads(flow_data)
            flow_elements = ["```mermaid", "flowchart TD"]
            for node in data.get('nodes', []):
                flow_elements.append(f"    {node['id']}[{node['label']}]")
            for edge in data.get('edges', []):
                flow_elements.append(f"    {edge['from']} --> {edge['to']}")
            flow_elements.append("```")
            return '\n'.join(flow_elements)
        except Exception as e:
            logger.error(f"Flowchart generation error: {str(e)}")
            return f"<!-- Error generating flowchart: {str(e)} -->"

class ResponseFormatter:
    DOCUMENT_TYPES = {
        'report': '📊',
        'case': '📱',
        'study': '📚',
        'analysis': '📈',
        'default': '📄'
    }

    @staticmethod
    def get_document_emoji(filename: str) -> str:
        lower_filename = filename.lower()
        for doc_type, emoji in ResponseFormatter.DOCUMENT_TYPES.items():
            if doc_type in lower_filename:
                return emoji
        return ResponseFormatter.DOCUMENT_TYPES['default']

    @staticmethod
    def clean_filename(filename: str) -> str:
        cleaned = re.sub(r'[_-]+', ' ', filename)
        cleaned = ' '.join(word.capitalize() for word in cleaned.split())
        return cleaned.strip()

    @staticmethod
    def format_citations(citations: List[str], hyperlinks: List[str]) -> str:
        if not citations or not hyperlinks:
            return ""

        formatted_citations = []
        for index, (citation, hyperlink) in enumerate(zip(citations, hyperlinks), 1):
            if not citation or not hyperlink:
                continue

            try:
                filename = os.path.basename(citation).replace('%20', ' ')
                filename_parts = filename.split('__')
                filename = filename_parts[0] if filename_parts and filename_parts[0] else f"Source {index}"
                filename = ResponseFormatter.clean_filename(filename)
                if not filename:
                    filename = f"Source {index}"
                emoji = ResponseFormatter.get_document_emoji(filename)
                encoded_link = urllib.parse.quote(hyperlink, safe=':/?=&')
                formatted_citations.append(f"{emoji} [{filename}]({encoded_link})")
            except Exception as e:
                logger.error(f"Citation formatting error for index {index}: {str(e)}")
                formatted_citations.append(f"📄 [Source {index}]({hyperlink})")

        return "\n".join(formatted_citations) if formatted_citations else ""

class APIClient:
    def __init__(self, base_url: str, max_retries: int = 3, timeout: int = 30):
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout = timeout
        self.visualization_handler = DataVisualizationHandler()

    async def make_request(self, message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        data = {
            "query": message,
            "chat_history": chat_history or []
        }

        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    self.base_url,
                    data=json.dumps(data).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )

                async with asyncio.timeout(self.timeout):
                    response = await asyncio.to_thread(
                        lambda: json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
                    )
                return response

            except asyncio.TimeoutError:
                logger.error(f"Request timeout on attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    return {"error": "Service timeout. Please try again later."}
                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Request error: {str(e)}")
                return {"error": f"Service error: {str(e)}"}

    def process_response(self, response: Dict[str, Any]) -> str:
        if 'error' in response:
            return f"⚠️ **Error:** {response['error']}"

        try:
            answer = response.get('answer', '').strip()
            citations = response.get('citation', [])
            hyperlinks = response.get('hyperlink', [])

            # Process visualizations
            for marker, processor in [
                ('{chart:', self.visualization_handler.process_chart),
                ('{table:', self.visualization_handler.process_table),
                ('{flowchart:', self.visualization_handler.process_flowchart)
            ]:
                if marker in answer:
                    pattern = f'{marker}(.*?)' + '}'
                    matches = re.finditer(pattern, answer, re.DOTALL)
                    for match in matches:
                        original = match.group(0)
                        data = match.group(1)
                        replacement = processor(data)
                        answer = answer.replace(original, replacement)

            formatted_text = ["**Assistant:**", answer]
            citations_text = ResponseFormatter.format_citations(citations, hyperlinks)
            if citations_text:
                formatted_text.extend(["", "**Learn more:**", citations_text])

            return '\n'.join(formatted_text)

        except Exception as e:
            logger.error(f"Response processing error: {str(e)}")
            return "⚠️ **Error:** Unable to process the response. Please try again."

# Initialize components
api_client = APIClient(os.getenv("API_CLIENT_URL"))
app = FastAPI()

# FastAPI routes
@app.get("/")
async def root():
    code_verifier, code_challenge = generate_pkce_pair()
    SESSION['code_verifier'] = code_verifier
    auth_url = msal_app.get_authorization_request_url(
        SCOPE,
        redirect_uri=f"http://localhost:8001{REDIRECT_PATH}",
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
        redirect_uri=f"http://localhost:8001{REDIRECT_PATH}",
        code_verifier=code_verifier
    )
    
    if "access_token" in result:
        SESSION['user_email'] = result.get('id_token_claims', {}).get('preferred_username', 'Unknown')
        return RedirectResponse(url="http://localhost:8000")
    return {"error": "Authentication failed"}

@app.get("/chainlit")
async def chainlit():
    user_email = SESSION.get('user_email', 'Unknown')
    await cl.Message(content=f"👋 **Welcome, {user_email}!**").send()
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=http://localhost:8000/">')

# Chainlit event handlers
@cl.on_chat_start
async def start():
    actions = [
        *[cl.Action(
            name="ask_question",
            label=q["title"],
            description=q["question"],
            payload={"question": q["question"]}
        ) for q in STARTER_QUESTIONS]
    ]
    
    user_email = SESSION.get('user_email', 'Guest')
    await cl.Message(
        content=f"👋 **Welcome to AIDW Assistant, {user_email}!**\n\nI can help you with information about AI-driven workplace implementations. Select a starter question below or ask your own question.",
        actions=actions
    ).send()

@cl.action_callback("ask_question")
async def on_action(action):
    try:
        question = action.payload["question"]
        formatted_question = f"**Question:** {question}\n\n"
        
        async with cl.Step(name="Crafting your response, please wait..."):
            response = await api_client.make_request(question)
            text = api_client.process_response(response)
            combined_text = formatted_question + text
        
        await cl.Message(content=combined_text).send()
    except Exception as e:
        logger.error(f"Action error: {str(e)}")
        await cl.Message(content="⚠️ **Error:** Unable to process the question. Please try again.").send()

@cl.on_message
async def on_message(message: cl.Message):
    try:
        if not message.content.strip():
            await cl.Message(content="❌ **Please enter a valid question**").send()
            return

        chat_history = cl.user_session.get("chat_history", [])
        
        async with cl.Step(name="Crafting your response, please wait..."):
            response = await api_client.make_request(message.content, chat_history)
            text = api_client.process_response(response)
            
            # Update chat history
            chat_history.append({"role": "user", "content": message.content})
            chat_history.append({"role": "assistant", "content": text})
            cl.user_session.set("chat_history", chat_history)
            
            await cl.Message(content=text).send()
    except Exception as e:
        logger.error(f"Message error: {str(e)}")
        await cl.Message(
            content="⚠️ **Error:** Unable to process your message. Please try again or contact support if the issue persists."
        ).send()

@cl.on_logout
async def on_logout():
    try:
        # Clear session data
        cl.user_session.clear()
        SESSION.clear()
        
        # Clear local storage
        await cl.local_storage.clear()
        
        await cl.Message(content="👋 **You have been logged out. Thank you for using AIDW Assistant!**").send()
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")

def generate_pkce_pair():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8001)