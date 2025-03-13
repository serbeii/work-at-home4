from google import genai
import time
import requests
from dotenv import load_dotenv
import os
from Chatbot import Chatbot


def start_app(chatbot):
    chatbot.start_chat()


if __name__ == "__main__":
    # start initialization
    load_dotenv()
    API_KEY = os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=API_KEY)
    database = "database/Northwind.db"

    model_name = "gemini-2.0-flash"

    models_list = client.models.list(config={"page_size": 5})
    model = None

    for model1 in models_list:
        if model1.name == "models/" + model_name:
            model = model1
            break

    # end initialization
    chatbot = Chatbot(client, model, database)
    start_app(chatbot)
