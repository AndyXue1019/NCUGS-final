import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')

client = genai.Client(api_key=api_key)
model_name = 'gemini-3.5-flash-lite'

prompt = '今天是幾越幾號(GMT+8)'
response = client.models.generate_content(
    model=model_name,
    contents=prompt
)

answer = response.text
print(answer)