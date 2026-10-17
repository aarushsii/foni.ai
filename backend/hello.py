import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url="https://api.nicrron.ai/v1", api_key=os.environ["NICRRON_API_KEY"])

reply = client.chat.completions.create(
    model="nicrron/auto",
    messages=[{"role": "user", "content": "Hello, MONEY TALKS!"}],
)
print(reply.choices[0].message.content)