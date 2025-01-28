import chainlit as cl
import random

# Starter questions
STARTER_QUESTIONS = [
    "What was the database that was used the most frequently in all AIDW that used the 'Chat with Your data' technical pattern?",
    "Which use case achieved the highest ACR in the Retail Industry in the EMEA market?",
    "List the top 10 partners who delivered the most AIDW?",
    "What other generative AI models did customers use that were not Azure OpenAI?",
    "How many agentic solutions were developed? What were their core services and/or architecture frameworks that were most commonly used?",
    "Summarize the reasons why we won"
]

# Helper function to clean and format responses
def clean_and_format_response(raw_response):
    """Clean and format the raw response for better readability."""
    cleaned_response = raw_response.strip()
    return cleaned_response

@cl.on_chat_start
async def on_chat_start():
    """Handle the start of a chat session."""
    # Select 4 random starter questions
    selected_questions = random.sample(STARTER_QUESTIONS, 4)

    elements = []
    for idx, q in enumerate(selected_questions):
        elements.append(
            cl.Text(content=q, name=f"starter_question_{idx}")
        )

    await cl.Message(
        content="Welcome to AIDW Assistant! Here are some questions you can ask:",
        elements=elements
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages from the user."""
    try:
        if not message.content.strip():
            await cl.Message(content="Please enter a valid question.").send()
            return

        # Mock response for demonstration purposes
        mock_response = f"You asked: '{message.content}'. Here's a placeholder response."
        formatted_response = clean_and_format_response(mock_response)

        # Store chat history in the user session
        chat_history = cl.user_session.get("chat_history", [])
        chat_history.append({"role": "user", "content": message.content})
        chat_history.append({"role": "assistant", "content": formatted_response})
        cl.user_session.set("chat_history", chat_history)

        await cl.Message(content=formatted_response).send()

    except Exception as e:
        await cl.Message(content=f"An error occurred: {str(e)}").send()

if __name__ == '__main__':
    cl.run()