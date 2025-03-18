from google import genai
from dotenv import load_dotenv
import os
import gradio as gr
from Chatbot import Chatbot


DEBUG_MODE = False


def chat(message, history):
    global chatbot
    global DEBUG_MODE
    result = chatbot.query(prompt=message, debug_mode=DEBUG_MODE)
    return result


def update_debug_state(debug_value):
    global DEBUG_MODE
    DEBUG_MODE = debug_value
    return f"Debug mode is now: {debug_value}"


if __name__ == "__main__":
    # start initialization
    global chatbot
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

    database_name = "file:database/Northwind.db?mode=ro"

    chatbot = Chatbot(client, model, database_name)

    with gr.Blocks() as demo:
        chatbot_interface = gr.ChatInterface(
            fn=chat, type="messages", title="Debug Chat", description="Hello world"
        )
        debug_checkbox = gr.Checkbox(False, label="Enable Debug Mode")
        debug_checkbox.change(fn=update_debug_state, inputs=debug_checkbox)
    demo.launch()
