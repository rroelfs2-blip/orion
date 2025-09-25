# File: backend/app/routers/chat.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

@router.post("/chat")
def chat_with_ai(req: ChatRequest):
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful financial assistant."},
                {"role": "user", "content": req.message},
            ],
            temperature=0.7,
            max_tokens=256
        )

        return {"response": response.choices[0].message.content.strip()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
