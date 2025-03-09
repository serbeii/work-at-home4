from google import genai
import time
import requests
from dotenv import load_dotenv
import os
from Chatbot import Chatbot

BLUE = "\033[94;1m"
RED = "\033[91;1m"
RESET = "\033[0m"
DEBUG = False

gist_url = "https://gist.githubusercontent.com/serbeii/7887216a6719cd2442cbe303e283e191/raw/848b621c990122ba1d41f8fee0864d3458a0d249/evil_text.txt"

gist_response = requests.get(gist_url)

evil_text = gist_response.text

def start_app(chatbot):
    chatbot.start_chat()


if __name__ == "__main__":
    # start initialization
    load_dotenv()
    API_KEY = os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=API_KEY)

    model_name = "gemini-2.0-flash"

    models_list = client.models.list(config={"page_size": 5})
    model = None

    for model1 in models_list:
        if model1.name == "models/" + model_name:
            model = model1
            break

    # end initialization
    chatbot = Chatbot(client, model)
    start_app(chatbot)
