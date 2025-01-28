import chainlit as cl
import urllib.request
import json
import ssl
import os
import textwrap
import re
import random

# Azure ML Endpoint Configuration
def configure_azure_endpoint():
    def allowSelfSignedHttps(allowed):
        if allowed and not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None):
            ssl._create_default_https_context = ssl._create_unverified_context

    allowSelfSignedHttps(True)

    return {
        'url': "https://prj-aidw-chat-assistant-01.eastus.inference.ml.azure.com/score",
        'api_key': "ZpIWFa6rectz1qjkAyDHQPnGvlO9HpCC"
    }

# Starter questions
STARTER_QUESTIONS = [
    "What was the database that was used the most frequently in all AIDW that used the 'Chat with Your data' technical pattern?",
    "Which use case achieved the highest ACR in the Retail Industry in the EMEA market?",
    "List the top 10 partners who delivered the most AIDW?",
    "What other generative AI models did customers use that were not Azure OpenAI?",
    "How many agentic solutions were developed? What were their core services and/or architecture frameworks that were most commonly used?",
    "Summarize the reasons why we won"
]

def clean_and_format_response(raw_response):
    cleaned_response = re.sub(r'<.*?>', '', raw_response)
    cleaned_response = re.sub(r'<br\s*/?>', '\n', cleaned_response)
    cleaned_response = re.sub(r'\n+', '\n', cleaned_response)
    cleaned_response = re.sub(r'\s{2,}', ' ', cleaned_response)
    return cleaned_response.strip()

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
                return parsed_result.get("answer", "Unexpected response format")
            return parsed_result
    except Exception as e:
        return f"Error: {str(e)}"

@cl.on_chat_start
async def on_chat_start():
    # Select 4 random starter questions
    selected_questions = random.sample(STARTER_QUESTIONS, 4)
    
    elements = []
    for q in selected_questions:
        elements.append(
            cl.Text(content=q, name=f"starter_question_{selected_questions.index(q)}")
        )

    await cl.Message(
        content="Welcome to AIDW Assistant! Here are some questions you can ask:",
        elements=elements
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    try:
        if not message.content.strip():
            await cl.Message(content="Please enter a valid question.").send()
            return

        chat_history = cl.user_session.get("chat_history", [])
        
        response = await query_azure_endpoint(message.content, chat_history)
        formatted_response = clean_and_format_response(response)
        wrapped_response = textwrap.fill(formatted_response, width=60)

        chat_history.append({"role": "user", "content": message.content})
        chat_history.append({"role": "assistant", "content": wrapped_response})
        cl.user_session.set("chat_history", chat_history)

        await cl.Message(content=wrapped_response).send()

    except Exception as e:
        await cl.Message(content=f"An error occurred: {str(e)}").send()

if __name__ == '__main__':
    cl.run()
