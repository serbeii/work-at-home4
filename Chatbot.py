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
    def __init__(self, client, model_name):
        self.database = "database/Northwind.db"
        self.create_tables = []
        self.client = client
        self.model_name = model_name
        self.chat_history = []
        self.chat_log = []
        # self.context_window_limit = model.input_token_limit + model.output_token_limit
        # self.input_token_limit = model.input_token_limit
        # self.output_token_limit = model.output_token_limit
        self.start_time = 0
        self.waiting_time = 0
        self.chat = None
        self.start_chat()

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
            print("Warning: Context window is almost full.")
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

        index1 = query.find("```sql")
        index2 = (
            query[index1 + 6 :].find("```") + index1 + 6
        )  # get the sql query from the output

        if index1 != -1 and index2 != -1:
            query1 = query[index1 + 6 : index2]
        else:
            print("Can not query the database based on the given prompt")
            return
        try:
            cursor.execute(query1)

        except Exception as e:
            if try_count == 3:
                print("Can not query the database based on the given prompt")
                return
            self._query(
                "you have made this error: {e} \n provide the correct query",  # retry the query, providing the error
                try_count + 1,
            )
            return

        # Fetch all results
        results = cursor.fetchall()

        # Close the connection
        conn.close()

        for result in results:
            print(f"{BLUE}{result}{RESET}")

    def get_response(self):  # api call to get the response (unused)
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

    def _query(self, prompt):  # query function (unused)
        if self._check_for_exceptions(prompt) == 1:  # check for exceptions
            return

        self.chat_history.append(
            ("User", prompt)
        )  # append the user's prompt to the chat history

        response = self.get_response()  # get the response from the chatbot (unused)

        if (
            response == ""
        ):  # if the response is empty == exepction occured, pop the last chat history
            self.chat_history.pop()
            return

        self.chat_history.append(("Gemini", response.text))

        current_token_count = self.get_token_count(
            "\n".join([f"{user}: {message}" for user, message in self.chat_history])
        )
        info = (
            "Context Window: "
            + str(current_token_count)
            + f" / {self.context_window_limit}"
        )

        print(f"{RED}{info}{RESET}")
        self._query_database(response.text, 0)

    def start_chat(self):
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
                        text="""You are a LLM who understands and can respond only in Turkish or English based on the language of user's input. If user talks in Turkish, respond in Turkish. If user talks in English, then respond in English.
                                You are prohibited to answer in any other language.  I am the user, a company manager who's working with a SQLite database. 
                                Your task is to extract relevant information from my natural language query, transform it into a valid SQL statement, execute that statement on the SQLite database, and return the results. 
                                Your response will always composed of a text message, a certainty as a value between 0 and 1, an sql statement and a structured output in JSON format as provided in: 
                                {
                                "type": "object",
                                "properties": {
                                    "certainty": {
                                    "type": "number",
                                    "description": "Confidence level in the SQL query or information provided (a value between 0 and 1)"
                                    },
                                    "sql": {
                                    "type": "string",
                                    "description": "The SQL query that was generated or used to retrieve information."
                                    },
                                    "message": {
                                    "type": "string",
                                    "description": "A conversational message providing context, results, or next steps.  In this case, something about the user and a query."
                                    }
                                },
                                "required": [
                                    "certainty",
                                    "sql",
                                    "message"
                                ]
                                }
                            """
                    ),
                ],
                response_schema={
                    "type": "object",
                    "properties": {
                        "certainty": {
                            "type": "number",
                            "description": "Confidence level in the SQL query or information provided (a value between 0 and 1)"
                        },
                        "sql": {
                            "type": "string",
                            "description": "The SQL query that was generated or used to retrieve information."
                        },
                        "message": {
                            "type": "string",
                            "description": "A conversational message providing context, results, or next steps.  In this case, something about the user and a query.",
                        }
                    },
                    "required": [
                        "certainty",
                        "sql",
                        "message"
                        ]
                }
            )
            
            # Create a chat session with the config
            self.chat = self.client.chats.create(
                model=self.model_name,
                config=generate_content_config
            )

    def chat_prompt(self, prompt):
        try:
            response = self.chat.send_message(prompt)
            fields = json.loads(response.text)
            message = fields["message"]
            if fields["certainty"] >= 0.8 and (query := fields["sql"]):
                message = message + "\n" + fields["sql"]
                print(message)
            return response
        except Exception as e:
            if self._fix_exceptions(e) == 1:
                return ""

            return self.chat_prompt(prompt)
