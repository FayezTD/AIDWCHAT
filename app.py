from flask import Flask, jsonify, request
import chainlit as cl
import urllib.request
import json
import ssl
import os
import textwrap
import logging
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
import re
from flask_cors import CORS

# Create Flask application instance
app = Flask(__name__)
CORS(app)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom exception for Azure endpoint errors
class AzureEndpointError(Exception):
    pass

# Azure ML Endpoint Configuration
def configure_azure_endpoint():
    def allowSelfSignedHttps(allowed):
        if allowed and not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None):
            ssl._create_default_https_context = ssl._create_unverified_context

    allowSelfSignedHttps(True)

    endpoint_config = {
        'url': "https://prj-aidw-chat-assistant-01.eastus.inference.ml.azure.com/score",
        'api_key': "ZpIWFa6rectz1qjkAyDHQPnGvlO9HpCC"
    }

    if not endpoint_config['api_key']:
        raise ValueError("API key is missing. Please check your .env file.")

    return endpoint_config

# Function to clean up and format the response
def clean_and_format_response(raw_response):
    cleaned_response = re.sub(r'<.*?>', '', raw_response)
    cleaned_response = re.sub(r'<br\s*/?>', '\n', cleaned_response)
    cleaned_response = re.sub(r'\n+', '\n', cleaned_response)
    cleaned_response = re.sub(r'\s{2,}', ' ', cleaned_response)
    cleaned_response = cleaned_response.strip()
    return cleaned_response

# Function to query the Azure endpoint with retry logic
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def query_azure_endpoint(message_content, chat_history=None):
    if chat_history is None:
        chat_history = []

    endpoint_config = configure_azure_endpoint()
    
    data = {
        "question": message_content,
        "chat_history": chat_history
    }
    body = str.encode(json.dumps(data))

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {endpoint_config["api_key"]}'
    }

    try:
        req = urllib.request.Request(endpoint_config['url'], body, headers)
        with urllib.request.urlopen(req) as response:
            result = response.read()
            parsed_result = json.loads(result)
            
            if isinstance(parsed_result, dict):
                if "error" in parsed_result:
                    raise AzureEndpointError(f"Azure Endpoint Error: {parsed_result['error']}")
                elif "answer" in parsed_result:
                    return parsed_result["answer"]
                else:
                    return "Unexpected response format"
            elif isinstance(parsed_result, str):
                return parsed_result
            else:
                raise AzureEndpointError(f"Unexpected response type: {type(parsed_result)}")
    except urllib.error.HTTPError as error:
        error_message = error.read().decode('utf8', 'ignore')
        raise AzureEndpointError(f"HTTP Error: {error.code} - {error_message}")
    except json.JSONDecodeError:
        raise AzureEndpointError("Invalid JSON response from endpoint")
    except Exception as e:
        raise AzureEndpointError(f"Unexpected error: {str(e)}")

# Chainlit event handlers
@cl.on_chat_start
async def on_chat_start():
    try:
        clear_action = cl.Action(
            name="clear_chat",
            payload={"action": "clear"},
            label="🗑️ Clear Chat",
            description="Clear the current conversation"
        )

        await cl.Message(
            content="👋 Welcome to AI Assistant! How can I help you today?",
            actions=[clear_action]
        ).send()

    except Exception as e:
        logger.error(f"Initialization error: {str(e)}")
        await cl.Message(
            content="⚠️ An error occurred during initialization. Please try again later."
        ).send()

@cl.action_callback("clear_chat")
async def clear_chat(action):
    cl.user_session.clear()
    await cl.Message(content="Chat cleared! Starting fresh...").send()
    await on_chat_start()

@cl.on_message
async def on_message(message: cl.Message):
    try:
        if not message.content.strip():
            await cl.Message(content="Please enter a valid question.").send()
            return

        if len(message.content) > 1000:
            await cl.Message(content="Please keep your questions under 1000 characters.").send()
            return

        async with cl.Step(" "):
            chat_history = cl.user_session.get("chat_history", [])
            try:
                response = await query_azure_endpoint(message.content, chat_history)
                formatted_response = clean_and_format_response(response)
            except AzureEndpointError as e:
                logger.error(f"Azure endpoint error: {str(e)}")
                await cl.Message(content="⚠️ We're experiencing technical difficulties. Please try again later.").send()
                return

            wrapped_response = textwrap.fill(formatted_response, width=60)

            chat_history.append({"role": "user", "content": message.content})
            chat_history.append({"role": "assistant", "content": wrapped_response})
            cl.user_session.set("chat_history", chat_history)

            feedback_actions = [
                cl.Action(name="feedback", payload={"type": "helpful"}, label="👍 Helpful"),
                cl.Action(name="feedback", payload={"type": "not_helpful"}, label="👎 Not Helpful"),
                cl.Action(
                    name="clear_chat",
                    payload={"action": "clear"},
                    label="🗑️ Clear Chat",
                    description="Clear the current conversation"
                )
            ]

            await cl.Message(
                content=wrapped_response,
                actions=feedback_actions
            ).send()

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        await cl.Message(
            content="⚠️ An unexpected error occurred. Please try again or contact support."
        ).send()

@cl.action_callback("feedback")
async def on_feedback(action):
    try:
        feedback_type = action.payload["type"]

        if feedback_type == "helpful":
            await cl.Message(content="Thank you for your positive feedback! 😊").send()
        else:
            await cl.Message(
                content="I'm sorry the response wasn't helpful. Would you like to rephrase your question?"
            ).send()

        await cl.Message(
            content="Feel free to ask another question or restart the chat."
        ).send()

    except Exception as e:
        logger.error(f"Error processing feedback: {str(e)}")
        await cl.Message(
            content="⚠️ An error occurred while processing your feedback. Please try again."
        ).send()

@cl.on_chat_end
async def on_chat_end():
    try:
        await cl.Message(
            content="👋 Thank you for using our AI Assistant! Have a great day!"
        ).send()
    except Exception as e:
        logger.error(f"Error in chat end handler: {str(e)}")

# Flask routes
@app.route('/')
def index():
    return "AI Assistant is running"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
