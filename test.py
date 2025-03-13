from google import genai
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=API_KEY)

from pydantic import BaseModel


class Recipe(BaseModel):
    recipe_name: str
    ingredients: list[str]


response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="List a few popular cookie recipes. Be sure to include the amounts of ingredients.",
    config={
        "response_mime_type": "application/json",
    },
)
# Use the response as a JSON string.
pydantic_response = r
print(response.text)

# Use instantiated objects.
my_recipes: list[Recipe] = response.parsed
