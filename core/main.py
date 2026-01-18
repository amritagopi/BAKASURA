import sys
import os
import asyncio

# FORCE UTF-8 for Windows Consoles
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# FIX FOR WINDOWS PLAYWRIGHT: Force ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from agent import app as agent_app, TargetProfile
from memory import save_memory

import logging
import traceback
from fastapi import Request
from fastapi.responses import JSONResponse

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("backend.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bakasura Brain API")

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = f"CRITICAL ERROR: {str(exc)}\n{traceback.format_exc()}"
    logger.error(error_msg)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error. Check backend.log for details.", "trace": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming Request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response Status: {response.status_code}")
    return response

@app.get("/")
async def root():
    return {"status": "online", "system": "Bakasura Brain", "version": "0.1.2"}

# --- API Models ---

class ProfileInput(BaseModel):
    """Reflects the TargetProfile schema for JSON input"""
    name: str
    city: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    nickname: Optional[str] = None
    other_clues: Optional[str] = None

class AnalysisRequest(BaseModel):
    """Request payload from the Frontend"""
    profile: ProfileInput

# --- Endpoints ---

@app.get("/")
def health_check():
    return {"status": "alive", "message": "Bakasura is hungry."}

@app.post("/analyze")
async def analyze_target(request: AnalysisRequest):
    """
    Triggers the LangGraph workflow.
    """
    # Convert Pydantic model to Dict for the Agent State
    profile_dict = request.profile.model_dump()
    
    # Initialize State
    initial_state = {
        "messages": [],
        "profile": profile_dict,
        "gathered_data": [],
        "hypocrisy_score": 0.0
    }
    
    try:
        # Run the graph
        # Run the graph
        # invoke() runs until the end. specific for synchronous-style call
        # We switched to async nodes for Playwright compability, so we MUST use ainvoke
        result = await agent_app.ainvoke(initial_state)
        
        # Extract the final response from the LLM
        final_messages = result.get("messages", [])
        last_message = final_messages[-1].content if final_messages else "No thoughts."
        
        # AUTO-FIX: Ensure LLM response is a clean string (Frontend expects string)
        # If LLM returned raw JSON with markdown code blocks, strip them.
        import json
        clean_response_str = last_message
        try:
             if isinstance(last_message, str):
                 # CLEANUP: Remove markdown ```json ... ``` wrappers
                 if "```" in last_message:
                     clean_response_str = last_message.replace("```json", "").replace("```", "").strip()
                 # Verify it's valid JSON (optional check)
                 # json.loads(clean_response_str) 
        except Exception:
            pass # Keep original if parsing fails

        gathered_data = result.get("gathered_data", [])
        
        # Save to Obsidian/Memory
        try:
            memory_file = save_memory(profile_dict, clean_response_str, gathered_data)
            print(f"Memory saved: {memory_file}")
        except Exception as e:
            print(f"[WARN] Memory loss: {e}")

        return {
            "status": "completed",
            "response": clean_response_str, # Return STRING to avoid React "Object not valid child" error
            "gathered_data": gathered_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # loop="asyncio" uses the standard asyncio policy we set at the top of the file
    # reload=False is CRITICAL on Windows because the reloader spawns child processes 
    # that might reset the loop policy or fail to inherit it correctly.
    print("[SYSTEM] Starting Bakasura Brain on Windows Proactor Loop...")
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=False, loop="asyncio")
