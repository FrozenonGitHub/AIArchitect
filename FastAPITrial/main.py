from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
import requests
import json
from bs4 import BeautifulSoup
from typing import Optional, List
from datetime import datetime

# Import services and models
from services.chroma_service import ChromaService
from services.document_processor import DocumentProcessor
from services.embedding_service import EmbeddingService
from models.schemas import (
    ChatRequest, ChatResponse, SessionCreate, SessionResponse,
    SearchRequest, SearchResult, MessageResponse, DocumentResponse,
    DocumentUpload
)
from utils.file_utils import (
    calculate_file_hash, get_file_extension, get_storage_path,
    get_file_size, format_file_size
)
import config

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize OpenAI client with custom base URL
client = OpenAI(
    api_key=os.getenv("COURSE_API_KEY"),
    base_url="https://space.ai-builders.com/backend/v1"
)

# Web search function
def web_search(query: str) -> dict:
    """Call the internal search API to search the web."""
    url = "https://space.ai-builders.com/backend/v1/search/"
    headers = {
        "Authorization": f"Bearer {os.getenv('COURSE_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "keywords": [query],
        "max_results": 3
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

# Read page function
def read_page(url: str) -> str:
    """Fetch a URL and extract the main text content from HTML."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        # Limit text length to avoid overwhelming the LLM
        max_length = 8000
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[Content truncated...]"

        return text
    except Exception as e:
        return f"Error reading page: {str(e)}"

# Tool schema for LLM function calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use this when you need up-to-date information or facts about recent events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_page",
            "description": "Fetch and read the content of a web page. Use this when you need to read detailed information from a specific URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the page to read"
                    }
                },
                "required": ["url"]
            }
        }
    }
]

class ChatRequest(BaseModel):
    user_message: str

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/hello/{input_text}")
async def hello(input_text: str):
    return {"message": f"Hello, World {input_text}"}

@app.post("/chat")
async def chat(request: ChatRequest):
    # Initialize conversation with user message
    messages = [
        {"role": "user", "content": request.user_message}
    ]

    max_turns = 5

    # Agentic loop
    for turn in range(max_turns):
        print(f"\n{'='*60}")
        print(f"[Turn {turn + 1}/{max_turns}]")
        print(f"{'='*60}")

        # Call LLM with current messages and available tools
        response = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            tools=tools
        )

        message = response.choices[0].message

        # Check if the LLM wants to call a tool
        if message.tool_calls:
            # Add assistant's message with tool calls to conversation
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            # Execute each tool call
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                print(f"[Agent] Decided to call tool: '{function_name}'")
                print(f"[Agent] Arguments: {arguments}")

                # Execute the tool
                if function_name == "web_search":
                    result = web_search(arguments["query"])
                    print(f"[System] Tool Output: {json.dumps(result, indent=2)}")

                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
                elif function_name == "read_page":
                    result = read_page(arguments["url"])
                    print(f"[System] Tool Output (first 500 chars): {result[:500]}...")

                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })

            # Continue the loop to let LLM process the tool results
            continue
        else:
            # No tool calls, LLM has provided final answer
            # Add final assistant message to history
            messages.append({
                "role": "assistant",
                "content": message.content
            })

            # Print complete message history
            print(f"\n{'='*60}")
            print("[System] COMPLETE MESSAGE HISTORY")
            print(f"{'='*60}")
            print(json.dumps(messages, indent=2))
            print(f"{'='*60}\n")

            print(f"[Agent] Final Answer: {message.content}")
            return {"response": message.content}

    # If we've exhausted max_turns, return the last message
    print(f"\n{'='*60}")
    print("[System] COMPLETE MESSAGE HISTORY (Max turns reached)")
    print(f"{'='*60}")
    print(json.dumps(messages, indent=2))
    print(f"{'='*60}\n")

    print(f"[System] Max turns ({max_turns}) reached")
    return {"response": message.content if message.content else "I apologize, but I couldn't complete the task within the available turns."}
