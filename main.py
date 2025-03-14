from google import genai
import time
import requests
from dotenv import load_dotenv
import os
import gradio as gr
from Chatbot import Chatbot


def start_app(chatbot):
    chatbot.start_chat()


#load_dotenv()
#API_KEY = os.getenv("GOOGLE_API_KEY")
#client = genai.Client(api_key=API_KEY)
#model_name = "gemini-2.0-flash-lite"
#chatbot = Chatbot(client, model_name)


def test(message, history):
    global chatbot
    result = chatbot.chat_prompt(message)
    return result


if __name__ == "__main__":
    # start initialization
    load_dotenv()
    API_KEY = os.getenv("GOOGLE_API_KEY")

    client = genai.Client(api_key=API_KEY)
    model_name = "gemini-2.0-flash-lite"

    models_list = client.models.list(config={"page_size": 5})  # get the list of models
    model = None

    for model1 in models_list:  # find the model: gemini-2.0-flash-lite
        if model1.name == "models/" + model_name:
            model = model1
            break

    chatbot = Chatbot(client, model_name)
    # end initialization
    demo = gr.ChatInterface(
        test, type="messages", title="work@home4", description="Lorem Ipsum Dolor"
    )  # create a chat interface
    demo.launch()  # launch the chat interface
    # start_app(chatbot)
