from google import genai
import time
import requests
from pydantic import BaseModel
import sqlite3

BLUE = "\033[94;1m"
RED = "\033[91;1m"
RESET = "\033[0m"
DEBUG = False


gist_url = "https://gist.githubusercontent.com/serbeii/7887216a6719cd2442cbe303e283e191/raw/848b621c990122ba1d41f8fee0864d3458a0d249/evil_text.txt"

gist_response = requests.get(gist_url)

evil_text = gist_response.text


class Chatbot:
    def __init__(self, client, model):
        self.database = "database/Northwind.db"
        self.create_tables = []
        self.client = client
        self.model = model
        self.chat_history = []
        self.chat_log = []
        self.context_window_limit = model.input_token_limit + model.output_token_limit
        self.input_token_limit = model.input_token_limit
        self.output_token_limit = model.output_token_limit
        self.start_time = 0
        self.waiting_time = 0

    def get_create_tables(self):
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

    def _start_timer(self):
        self.start_time = time.time()

    def _get_time(self):
        return time.time() - self.start_time

    def get_token_count(self, text):
        try:
            token_text = str(
                self.client.models.count_tokens(model=self.model.name, contents=text)
            ).split(" ")
            index = token_text[0].index("=") + 1
            token = int(token_text[0][index:])
            return token
        except Exception as e:
            return 0

    def _shrink_chat_history(self, prompt):
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
            self.chat_history = self.chat_history[1:]
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
            return 0
        else:
            print(f"An error occurred: {e}")
            return 1  # failsafe

    def start_chat(self):
        while True:
            prompt = ""
            genmode = ""

            genmode = input(
                """Please choose one of the following options:
            *Enter 't' to enter a text prompt.
            *Enter 'c' to start a chat.
            *Enter 'f' to prefill the history.
            *Enter 'p' to print chat history.
            *Enter 'b' to break rpm limit
            *Enter 'q' to quit.
            *Enter 'query' to query the sql lite database, json format.
            Option: """
            )
            self.chat_log += self.chat_history
            self.chat_history = []

            if genmode == "q":  # quit
                print("Exiting the application.")
                break

            elif genmode == "f":  # prefill
                if self.start_time == 0:
                    self._start_timer()

                prompt = evil_text

                while True:
                    self._chat(prompt)

                    prefill_again = input(
                        "would you like to fill the history more ? y/n \n"
                    )
                    if prefill_again == "y":
                        prompt = evil_text
                        continue

                    if prompt == "q":
                        break

                    prompt = input()

            elif genmode == "p":  # print chat log
                print("\nChat History:\n")
                for user, message in self.chat_log:
                    print(f"{user}: {message}")
                print("\n")

            elif genmode == "t":  # enter text

                prompt = input("Enter your text: \n")

                if prompt == "q":
                    continue

                if self.start_time == 0:
                    self._start_timer()

                self._chat(prompt)

            elif genmode == "c":  # chat

                if self.start_time == 0:
                    self._start_timer()

                prompt = "Hello"

                while True:
                    self._chat(prompt)
                    prompt = input()

                    if prompt == "q":
                        genmode = ""
                        break

            elif genmode == "b":  # break limits

                if self.start_time == 0:
                    self._start_timer()

                while True:
                    self._chat("Hello World!")

            elif genmode == "query":
                self.chat_history.append(
                    (
                        "System",
                        "process user's request to an sql query, based on the provided tables below",
                    )
                )

                if self.create_tables == []:
                    self.create_tables = self.get_create_tables()

                self.chat_history.append(("System", "\n".join(self.create_tables)))

                print("Enter your query in natural language")

                while True:
                    prompt = input()

                    if prompt == "q":
                        break
                    self._query(prompt)

            else:
                continue

    def _query_database(self, query, try_count):
        conn = sqlite3.connect(self.database)
        cursor = conn.cursor()

        index1 = query.find("```sql")
        index2 = query[index1 + 6 :].find("```") + index1 + 6

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
                "you have made this error: {e} \n provide the correct query",
                try_count + 1,
            )
            return

        # Fetch all results
        results = cursor.fetchall()

        # Close the connection
        conn.close()

        for results1 in results:
            print(results1)

    def _query(self, prompt):
        if self._check_for_exceptions(prompt) == 1:
            return

        self.chat_history.append(("User", prompt))

        response = self.get_response()

        if response == "":
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

    def _chat(self, prompt):  # chatting function

        if self._check_for_exceptions(prompt) == 1:
            return

        self.chat_history.append(("User", prompt))

        response = self.get_response()

        if response == "":
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
        print(f"{BLUE}{response.text}{RESET}", end="")

    def get_response(self):  # api call
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
