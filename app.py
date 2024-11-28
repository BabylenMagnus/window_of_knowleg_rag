import os
# Disable ChromaDB telemetry
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

import json
import chromadb
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Literal
import logging

# Add basic logging configuration
logging.basicConfig(level=logging.INFO)

from engine import model, prompt_template, semantic_search
from add_data import add_into_collection
from db import (
    get_db_connection, create_storage, list_storages, 
    check_storage_nickname_exists, check_existing_records,
    get_chats, create_chat, get_chat_history, create_chat_history,
    list_models, ensure_dummy_model
)


chroma_client = chromadb.HttpClient(host='localhost', port=8027)


# Модели данных
class StorageCreate(BaseModel):
    name: str
    description: str = None


class ChatCreate(BaseModel):
    """
    Pydantic model for creating a new chat
    """
    name: str
    model_id: Optional[int] = None


class ChatHistoryCreate(BaseModel):
    """
    Pydantic model for creating a new chat history entry
    """
    chat_id: int
    text: str
    author: Literal['user', 'model']


async def query_simple_rag_stream(query: str, collection_name: str):
    results = semantic_search(query, collection_name)

    # Prepare the context and sources
    context_text = "\n\n---\n\n".join(results['documents'][0])
    sources = list(set([i['url'] for i in results['metadatas'][0]]))
    prompt = prompt_template.format(context=context_text, question=query)

    # Get the async stream from the model
    response_stream = model.astream(prompt)
    return response_stream, sources


app = FastAPI()

# Добавляем CORS middleware
origins = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8027"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get('/')
async def root():
    return PlainTextResponse("Здарова бандиты")


@app.get('/chatting')
async def chat_endpoint(request: Request):
    data = await request.json()
    query = data.get('query')
    collection_name = data.get('collection_name', 'test')

    response_stream, sources = await query_simple_rag_stream(query, collection_name)

    async def event_generator():
        # First, send the sources as a JSON event
        yield f"data: {json.dumps({'sources': sources})}\n\n"
        # Now, send the response content as events
        async for chunk in response_stream:
            yield f"data: {json.dumps({'content': chunk})}\n\n"

    return StreamingResponse(event_generator(), media_type='text/event-stream')


@app.post('/chatting_v2')
async def chat_endpoint_v2(request: Request):
    data = await request.json()
    query = data.get('query')
    collection_name = data.get('collection_name', 'test')

    response_stream, sources = await query_simple_rag_stream(query, collection_name)

    async def event_generator():
        # First, send the sources as a JSON event
        yield f"data: {json.dumps({'sources': sources})}\n\n"
        # Now, send the response content as events
        async for chunk in response_stream:
            yield f"data: {json.dumps({'content': chunk})}\n\n"

    return StreamingResponse(event_generator(), media_type='text/event-stream')


@app.post("/add-url")
async def add_url_endpoint(request: Request):
    try:
        data = await request.json()
        url = data.get("url")
        collection_nickname = data.get("collection_nickname")
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
            
        if not collection_nickname:
            raise HTTPException(status_code=400, detail="Collection nickname is required")
            
        if not check_storage_nickname_exists(collection_nickname):
            raise HTTPException(status_code=404, detail="Storage with this nickname not found")
            
        add_into_collection(url, collection_nickname)
        return JSONResponse(content={"status": "success", "message": "Data added successfully"})
        
    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/storages")
async def create_storage_endpoint(storage: StorageCreate):
    try:
        result = create_storage(storage.name, storage.description)
        return JSONResponse(content={"status": "success", "data": result})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/list_storages")
async def list_storages_endpoint():
    try:
        result = list_storages()
        return JSONResponse(content={"status": "success", "data": result})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/check-records")
async def check_records_endpoint():
    try:
        result = check_existing_records()
        return JSONResponse(content={"status": "success", "data": result})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/chats")
async def list_chats():
    """
    Retrieve all chats, ordered by most recently updated.
    
    Returns:
        List of chat records
    """
    return get_chats()


@app.post("/chats")
async def add_chat(chat_data: ChatCreate):
    """
    Create a new chat.
    
    Args:
        chat_data (ChatCreate): Data for creating a new chat, including name and optional model_id
    
    Returns:
        Dict representing the newly created chat
    """
    return create_chat(
        name=chat_data.name, 
        model_id=chat_data.model_id
    )


@app.get("/chat_history/{chat_id}")
async def retrieve_chat_history(chat_id: int):
    """
    Retrieve chat history for a specific chat.
    
    Args:
        chat_id (int): ID of the chat to retrieve history for
    
    Returns:
        List of chat history records
    """
    return get_chat_history(chat_id)


@app.post("/chat_history")
async def save_chat_history(chat_history: ChatHistoryCreate):
    """
    Save a new chat history entry.
    
    Args:
        chat_history (ChatHistoryCreate): Data for creating a new chat history entry
    
    Returns:
        Dict representing the newly created chat history entry
    """
    return create_chat_history(
        chat_id=chat_history.chat_id,
        text=chat_history.text,
        author=chat_history.author
    )


@app.get("/models")
async def get_models():
    """
    Retrieve all available models.
    
    Returns:
        List of model records
    """
    return list_models()


def create_dummy_model_if_not_exists():
    """
    Create a dummy model with ID 1 if it doesn't exist in the models table.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Try to insert the dummy model, ignoring if it already exists
            cur.execute("""
                INSERT INTO models (
                    id, name, model_path, type, context_window
                ) VALUES (
                    1, 
                    'Dummy Model', 
                    '/dev/null', 
                    'service', 
                    2048
                ) 
                ON CONFLICT (id) DO NOTHING
            """)
            conn.commit()
    except Exception as e:
        logging.error(f"Error creating dummy model: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    import uvicorn
    # Create dummy model when the app starts
    create_dummy_model_if_not_exists()

    uvicorn.run(app, host='localhost', port=8040)
