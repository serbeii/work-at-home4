from google import genai
from google.genai import types
import time
import sqlite3
import json
import gradio as gr

DEBUG = False


class Chatbot:
    def __init__(self, client, model, database_name):
        self.database = database_name
        self.create_tables = []
        self.client = client
        self.model = model
        self.chat_history = []
        self.initial_instruction = f"""You are a LLM who understands and can respond only in Turkish or English based on the language of user's input. If user talks in Turkish, respond in Turkish. If user talks in English, then respond in English.
                                You are prohibited to answer in any other language.  I am the user, a company manager who's working with a SQLite database. Our database is SQLite.
                                Your task is to extract relevant information from my natural language query, transform it into a valid SQLite statement, which should be a single sql statement, along with a json schema for the sqlite output.
                                Your response will always composed of a text message, a certainty as a value between 0 and 1 which will determine if you need to give an SQL query to the user, an SQLite statement  when certainity is above 0.80 and a JSON schema for the possible SQLite output (Do not use Tab Indents).
                                The schema for the SQLite database is as follows:
                                """ + "\n".join(
            self.get_create_tables()
        )
        self.initial_schema = {
            "type": "object",
            "properties": {
                "certainty": {
                    "type": "number",
                    "description": "Confidence that an SQL query should be executed (a value between 0 and 1)",
                },
                "sql": {
                    "type": "string",
                    "description": "The SQL query that is to be generated to retrieve information. It should be a single SQL lite statement.",
                },
                "message": {
                    "type": "string",
                    "description": "A conversational message providing context, results, or next steps.  In this case, something about the user and a query.",
                },
                "schema": {
                    "type": "string",
                    "description": "The JSON schema of the expected output of the SQL query in compact format without extra whitespace. Define the properties and required keys of the JSON object based on the database schema and the query.",
                },
            },
            "required": ["certainty", "sql", "message", "schema"],
        }
        self.input_token_limit = model.input_token_limit - (
            len(self.initial_instruction) + len(json.dumps(self.initial_schema))
        )
        self.output_token_limit = model.output_token_limit
        self.context_window_limit = self.input_token_limit + self.output_token_limit
        self.start_time = 0
        self.waiting_time = 0
        self.chat = self.start_new_chat(
            self.get_config(self.initial_instruction, self.initial_schema)
        )
        self.exceptions = []

    def get_create_tables(
        self,
    ):  # get the create table queries from the database script
        script_content = open("database/database_script.sql", "r").read()
        tables = []
        index1 = script_content.find("CREATE")
        index2 = -1
        if index1 != -1:
            index2 = script_content[index1 + 6 :].find(";") + index1 + 6 + 1

        while index1 != index2 - 1 and index2 != index1 - 1:
            tables.append(script_content[index1:index2])
            index1 = script_content[index2:].find("CREATE") + index2
            if index1 != index2 - 1:
                index2 = script_content[index1:].find(";") + index1 + 1

        return tables

    def _start_timer(self):  # start the timer
        self.start_time = time.time()

    def _get_time(self):  # get the time since the timer started
        return time.time() - self.start_time

    def get_token_count(self, text):  # get the token count of a given text
        try:
            token_text = str(
                self.client.models.count_tokens(model=self.model.name, contents=text)
            ).split(" ")
            index = token_text[0].index("=") + 1
            token = int(token_text[0][index:])
            return token
        except Exception as e:
            return 0

    def _check_for_exceptions(
        self, prompt
    ):  # checks for possible exceptions and fixes them BEFORE using the api

        if self.get_token_count(prompt) >= self.input_token_limit:
            self.exceptions.append("Input window is full, please enter a shorter text.")
            return 1

        chat_history = self.get_chat_history() + prompt

        total_tokens = self.get_token_count(chat_history) + self.output_token_limit

        if total_tokens >= self.context_window_limit:
            self.exceptions.append(
                "Context window is full, therefore you will lose some of your chat history."
            )
            return 0
        elif total_tokens >= self.context_window_limit * 0.8:
            self.exceptions.append(
                "Input window is almost full. You might lose some of your chat history."
            )
            return 0

        return 0

    def _fix_exceptions(self, e):  # fixes unforseen exceptions

        if not hasattr(e, "code"):
            self.exceptions.append(f"An error occurred: {e}")
            return 1  # failsafe

        if self.waiting_time == 0:
            current_time = int(self._get_time() % 60)
            self.waiting_time = current_time

        else:
            current_time = 60 - self.waiting_time
            self.waiting_time = 0

        if e.code == 429:  # tpm or rpm
            self.exceptions.append(
                f"Resource exhausted, please wait {60 - current_time} seconds to continue"
            )

            # time.sleep(60 - current_time)
            return 0  # retry the function
        elif e.code == 400:
            self.exceptions.append(f"Bad request: {e}")
            return 1  # failsafe
        elif e.code == 503:
            self.exceptions.append(f"Service unavailable: {e}")
            return 1
        else:
            self.exceptions.append(f"An error occurred: {e}")
            return 1  # failsafe

    def _query_database(self, query, debug_mode, try_count):  # query database

        conn = sqlite3.connect(self.database, uri=True)
        cursor = conn.cursor()

        try:
            cursor.execute(query)
            results = cursor.fetchall()
            return results

        except Exception as e:
            if try_count == 3:
                self.exceptions.append(
                    "Can not query the database based on the given prompt: ", e
                )
                return ""
            self.query(
                "you have made this error: {e} \n provide the correct query",  # retry the query, providing the error
                debug_mode,
                try_count + 1,
            )
            return ""

        finally:
            # Close the connection
            conn.close()

    def query(self, prompt, debug_mode, try_count=0):  # query function (unused)
        if self._check_for_exceptions(prompt) == 1:  # check for exceptions
            return ""

        if self.start_time == 0:
            self._start_timer()

        message = ""
        try:
            response = self.chat.send_message(prompt)

            response_dict = json.loads(response.text)

            if debug_mode is True:
                message = response.text
            message = message + "\n" + response_dict["message"]

            if response_dict["schema"] == "":
                self.exceptions.append("Schema couldn't be created")
                return message

            schema = json.loads(response_dict["schema"])

            if response_dict["certainty"] >= 0.8:
                query_result = self._query_database(
                    response_dict["sql"], debug_mode, try_count
                )

                if query_result == "":
                    return message
                if debug_mode is True:
                    message = message + "\n" + json.dumps(query_result, indent=4)

                system_instruction = (
                    "Do not use your memory from your pretraining process or the chat history."
                    + "Only use the query output provided by the user"
                    + " to provide necessary information"
                )

                inner_prompt = "".join([str(row) for row in query_result])
                config = self.get_config(system_instruction, schema)
                next_response = self.chat.send_message(inner_prompt, config)
                next_response_dict = json.loads(next_response.text)
                message = message + "\n" + json.dumps(next_response_dict, indent=4)
            return message

        except Exception as e:
            if self._fix_exceptions(e) == 1:
                self.exceptions.append(f"An error occurred: {e}")
                return ""

            # return query(prompt)

    def get_config(self, instruction, schema):
        # Create configuration with system instruction
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_NONE",  # Block none
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_NONE",  # Block none
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_NONE",  # Block none
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_NONE",  # Block none
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_CIVIC_INTEGRITY",
                    threshold="BLOCK_NONE",  # Block none
                ),
            ],
            response_mime_type="application/json",
            system_instruction=[
                types.Part.from_text(
                    text=instruction,
                ),
            ],
            response_schema=schema,
        )

        return generate_content_config

    def start_new_chat(self, config):
        chat = self.client.chats.create(
            model=self.model.name,
            config=config,
        )
        return chat

    def get_chat_history(self):
        history = self.chat.get_history()
        if not history:
            return ""
        return "\n".join(str(item) for item in history)
