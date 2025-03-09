from google import genai
import time
import requests

BLUE = "\033[94;1m"
RED = "\033[91;1m"
RESET = "\033[0m"
DEBUG = False

class Chatbot:
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.chat_history = []
        self.chat_log = []
        self.context_window_limit = model.input_token_limit + model.output_token_limit
        self.input_token_limit = model.input_token_limit
        self.output_token_limit = model.output_token_limit
        self.start_time = 0
        self.waiting_time = 0

    def _start_timer(self):
        self.start_time = time.time()

    def _get_time(self):
        return time.time() - self.start_time

    def get_token_count(self, text):
        try:
            token_text = str(
                self.client.models.count_tokens(
                    model=self.model.name, contents=text)
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
                total_tokens >= self.context_window_limit or len(
                    self.chat_history) % 2 == 1
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
                system_prompt = "prior info"

                self.chat_history.append(("System", system_prompt))
                prompt = input("Enter your query in natural language\n")
                self._query()
                # ...

            else:
                continue

    def _query_database(self, query):
        pass

    def _query(self, prompt):
        pass

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
                "\n".join([f"{user}: {message}" for user,
                          message in self.chat_history])
            )
        info = (
                "Context Window: "
                + str(current_token_count)
                + f" / {self.context_window_limit}"
            )

        print(f"{RED}{info}{RESET}")
        print(f"{BLUE}{response.text}{RESET}", end="")

    def _text(self, prompt):  # texting function
        print("prompt:", prompt)

        if self._check_for_exceptions(prompt) == 1:
            return

        response = self.get_response()

        if response == "":
            return

        current_token_count = self.get_token_count(
                "\n".join([f"{user}: {message}" for user,
                          message in self.chat_history])
            )
        info = (
                "Context Window: "
                + str(current_token_count)
                + f" / {self.context_window_limit}"
            )

        print(f"{RED}{info}{RESET}")
        print(f"{BLUE}Gemini: {response.text}{RESET}")

    def get_response(self):  # api call
        try:
            response = self.client.models.generate_content(
                model=self.model.name,
                    contents="\n".join(
                        [f"{user}: {message}" for user,
                            message in self.chat_history]
                    ),
                )
            return response
        except Exception as e:
            if self._fix_exceptions(e) == 1:
                return ""

            return self.get_response()
