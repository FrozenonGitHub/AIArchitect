"""
Standalone FastAPI app for testing LLM connectivity.
"""
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel


# Load environment variables from repo .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Initialize OpenAI client with AI-Builders base URL
client = OpenAI(
    api_key=os.getenv("COURSE_API_KEY"),
    base_url="https://space.ai-builders.com/backend/v1",
)

app = FastAPI(title="FastAPITrial LLM Test", version="0.1.0")

# Mount static files if present
app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = "gpt-5"


class ChatResponse(BaseModel):
    response: str


@app.get("/")
async def root():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "FastAPITrial LLM Test API"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    try:
        result = client.chat.completions.create(
            model=request.model or "gpt-5",
            messages=[{"role": "user", "content": request.message}],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    content = result.choices[0].message.content
    return ChatResponse(response=content or "")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
