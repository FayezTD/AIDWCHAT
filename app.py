import chainlit as cl
import urllib.request
import json
import os
import ssl
import textwrap
import random

STARTER_QUESTIONS = [
    {
        "title": "💼 Summarize the reasons why we won",
        "question": "Summarize the reasons why we won"
    },
    {
        "title": "🤝 List the top 10 partners who delivered the most AIDW",
        "question": "List the top 10 partners who delivered the most AIDW"
    },
    {
        "title": "📈 Which use case achieved the highest ACR in the Retail Industry in the EMEA market?",
        "question": "Which use case achieved the highest ACR in the Retail Industry in the EMEA market?"
    },
    {
        "title": "🔍 What was the database that was used the most frequently in all AIDW that used the 'Chat with Your data' technical pattern?",
        "question": "What was the database that was used the most frequently in all AIDW that used the 'Chat with Your data' technical pattern?"
    }
]

def allowSelfSignedHttps(allowed):
    if allowed and not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None):
        ssl._create_default_https_context = ssl._create_unverified_context

allowSelfSignedHttps(True)

async def query_endpoint(message_content, chat_history=None):
    url = 'https://prj-aidw-chat-assistant-v1.eastus.inference.ml.azure.com/score'
    api_key = 'Bptpa5tMrK35YEIbOHiRmMGGgXIpVR30'

    if not api_key:
        raise Exception("API key is required to invoke the endpoint")

    data = {
        "question": message_content,
        "chat_history": chat_history if chat_history else []
    }

    body = str.encode(json.dumps(data))
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    try:
        req = urllib.request.Request(url, body, headers)
        response = urllib.request.urlopen(req)
        result = response.read()
        return json.loads(result)
    except urllib.error.HTTPError as error:
        error_message = f"Request failed with status code: {error.code}\n"
        error_message += error.read().decode("utf8", 'ignore')
        raise Exception(error_message)

@cl.on_chat_start
async def start():
    # Create action buttons for each question
    actions = []
    for q in STARTER_QUESTIONS:
        actions.append(
            cl.Action(
                name="ask_question",
                label=f"{q['title']}",
                description=q['question'],
                payload={"question": q['question']},
            )
        )

    await cl.Message(
        content="👋 Welcome to AIDW Assistant! I can help you analyze AIDW data and answer your questions.",
        actions=actions
    ).send()

@cl.action_callback("ask_question")
async def on_action(action):
    question = action.payload["question"]
    
    # Show the question being asked
    await cl.Message(content=question, author="User").send()
    
    try:
        response = await query_endpoint(question)
        
        if isinstance(response, dict):
            response_text = response.get("answer", str(response))
        else:
            response_text = str(response)
            
        wrapped_response = textwrap.fill(response_text, width=80)
        await cl.Message(content=wrapped_response).send()
        
    except Exception as e:
        await cl.Message(content=f"Error: {str(e)}").send()

@cl.on_message
async def on_message(message: cl.Message):
    try:
        if not message.content.strip():
            await cl.Message(content="Please enter a valid question.").send()
            return

        chat_history = cl.user_session.get("chat_history", [])
        response = await query_endpoint(message.content, chat_history)
        
        if isinstance(response, dict):
            response_text = response.get("answer", str(response))
        else:
            response_text = str(response)
            
        wrapped_response = textwrap.fill(response_text, width=80)

        chat_history.append({"role": "user", "content": message.content})
        chat_history.append({"role": "assistant", "content": wrapped_response})
        cl.user_session.set("chat_history", chat_history)

        await cl.Message(content=wrapped_response).send()

    except Exception as e:
        await cl.Message(content=f"Error: {str(e)}").send()

if __name__ == '__main__':
    cl.run(port=8000)
