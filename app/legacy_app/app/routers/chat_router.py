
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import os
import openai

router = APIRouter()

class ChatMessage(BaseModel):
    message: str

@router.post("/chat")
def chat(msg: ChatMessage, authorization: str = Header(None)):
    admin_token = os.getenv("ADMIN_TOKEN")
    if admin_token and authorization != f"Bearer {admin_token}":
        raise HTTPException(status_code=403, detail="Unauthorized")

    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        raise HTTPException(status_code=500, detail="Missing OpenAI key")

    try:
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": msg.message}],
            temperature=0.7
        )
        return {"response": res["choices"][0]["message"]["content"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
