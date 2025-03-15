from google import genai
from google.genai import types
import time
import requests
from pydantic import BaseModel
import sqlite3
from dotenv import load_dotenv
import os
import json

BLUE = "\033[94;1m"
RED = "\033[91;1m"
RESET = "\033[0m"
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
                                Your task is to extract relevant information from my natural language query, transform it into a valid SQLite statement along with a json schema for the sqlite output.
                                Your response will always composed of a text message, a certainty as a value between 0 and 1, an sqlite statement and a json schema for he possible sqlite output. 
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
                    "description": "The SQL query that was generated or used to retrieve information.",
                },
                "message": {
                    "type": "string",
                    "description": "A conversational message providing context, results, or next steps.  In this case, something about the user and a query.",
                },
                "schema": {
                    "type": "string",
                    "description": "The json schema of the output of the SQL query. Decide the properties and required keys of the json object based on the database schema and the query.",
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

    def _shrink_chat_history(self, prompt):  # shrinks the context window if it is full
        chat_history_str = "\n".join(
            [f"{user}: {message}" for user, message in self.chat_history]
        )
        total_tokens = (
            self.get_token_count(chat_history_str)
            + self.get_token_count(prompt)
            + self.output_token_limit
        )

        while (
            total_tokens >= self.context_window_limit or len(self.chat_history) % 2 == 1
        ):  # shrink until context window < limit or a chat is cut in half
            # shrink from the beginning

            self.chat_history = self.chat_history[1:]  # shrink from the beginning

            chat_history_str = "\n".join(
                [f"{user}: {message}" for user, message in self.chat_history]
            )
            total_tokens = (
                self.get_token_count(chat_history_str)
                + self.get_token_count(prompt)
                + self.output_token_limit
            )

    def _summarize_history(self):  # inactive
        pass

    def _check_for_exceptions(
        self, prompt
    ):  # checks for possible exceptions and fixes them BEFORE using the api
        if self.get_token_count(prompt) >= self.input_token_limit:
            print("Input window is full, please enter a shorter text.")
            return 1

        chat_history_str = "\n".join(
            [f"{user}: {message}" for user, message in self.chat_history]
        )
        total_tokens = (
            self.get_token_count(chat_history_str)
            + self.get_token_count(prompt)
            + self.output_token_limit
        )

        if total_tokens >= self.context_window_limit:
            print("Context window is full, therefore it will shrink.")
            self._shrink_chat_history(prompt)
            return 0
        elif total_tokens >= self.context_window_limit * 8 / 10:
            print("Warning: Context window is" " almost full.")
            return 0

        return 0

    def _fix_exceptions(self, e):  # fixes unforseen exceptions

        if not hasattr(e, "code"):
            print(f"An error occurred: {e}")
            return 1  # failsafe

        if self.waiting_time == 0:
            current_time = int(self._get_time() % 60)
            self.waiting_time = current_time
        else:
            current_time = 60 - self.waiting_time
            self.waiting_time = 0

        if e.code == 429:
            print(
                f"Resource exhausted, please wait {60 - current_time} seconds to continue"
            )
            time.sleep(60 - current_time)
            return 0  # retry the function
        else:
            print(f"An error occurred: {e}")
            return 1  # failsafe

    def _query_database(self, query, try_count):  # query database
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        try:
            cursor.execute(query)
            results = cursor.fetchall()
            return results

        except Exception as e:
            if try_count == 3:
                print("Can not query the database based on the given prompt")
                return ""
            # self.query(
            #     "you have made this error: {e} \n provide the correct query",  # retry the query, providing the error
            #     try_count + 1,
            # )
            return ""

        # Fetch all results
        #results = cursor.fetchall()
        finally:
        # Close the connection
            conn.close()

        #return results

    def get_JSON_response(self):
        try:
            response = self.client.models.generate_content(
                model=self.model.name,
                contents="\n".join(
                    [f"{user}: {message}" for user, message in self.chat_history]
                ),
            )
            return response
        except Exception as e:
            if self._fix_exceptions(e) == 1:
                return ""

            return self.get_response()

    def query(self, prompt, debug_mode):  # query function (unused)
        # if self._check_for_exceptions(prompt) == 1:  # check for exceptions
        #    return

        # self.chat_history.append(
        #    ("User", prompt)
        # )
        try:
            response = self.chat.send_message(prompt)

            response_dic = json.loads(response.text)

            response_str = "\n".join(
                [f"{key}: {value}" for key, value in response_dic.items()]
            )

            message = ""
            if debug_mode is True:
                message = response.text
            message = message + "\n" + response_dic["message"]

            if response_dic["schema"] == "":
                return message

            schema = json.loads(response_dic["schema"])

            if response_dic["certainty"] >= 0.8:
                query_result = self._query_database(response_dic["sql"], 0)

                if query_result == "":
                    return message

                instruction = (
                    "use this query_output:\n"
                    + response_dic["sql"]
                    + " to provide the json file"
                )
                config = self.get_config(instruction, schema)
                chat = self.start_new_chat(config)

                next_response = chat.send_message("Provide the json file")
                next_response_dic = json.loads(next_response.text)
                message = message + "\n" + json.dumps(next_response_dic, indent=4)
            return message

        except Exception as e:
            if self._fix_exceptions(e) == 1:
                print(f"An error occurred: {e}")
                return ""

        # current_token_count = self.get_token_count(
        #    "\n".join([f"{user}: {message}" for user, message in self.chat_history])
        # )

        # info = (
        #    "Context Window: "
        #    + str(current_token_count)
        #    + f" / {self.context_window_limit}"
        # )

        # print(f"{RED}{info}{RESET}")

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
