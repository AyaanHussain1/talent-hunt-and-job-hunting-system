import os
import requests
from dotenv import load_dotenv

load_dotenv("token.env", override=True)

token = os.getenv("Github_Token")

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
}

r = requests.get("https://api.github.com/user", headers=headers)

print(r.status_code)
print(r.text)