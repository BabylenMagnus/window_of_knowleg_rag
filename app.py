import os
import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Literal, Dict, Any, List

import chromadb
import aiofiles
import mimetypes
import aiohttp
import urllib.parse

from fastapi import (FastAPI, Request, HTTPException, File, Form, UploadFile, Body, status)
from fastapi.responses import (StreamingResponse, PlainTextResponse, JSONResponse)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# Disable ChromaDB telemetry
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('app.log', encoding='utf-8')]
)
logger = logging.getLogger(__name__)

# Import local modules
from engine import model, prompt_template, semantic_search
from add_data import add_into_collection
from db import (get_db_connection, create_storage, list_storages, check_storage_nickname_exists, check_existing_records,
                get_chats, create_chat, get_chat_history, create_chat_history, list_models, get_last_n_messages,
                update_storage, get_storage_files, get_file_details, get_storage_by_id, add_url_to_storage_collection,
                save_file, delete_storage_file, update_file_info)


# Utility Functions
def handle_exception(e: Exception, status_code: int = 500) -> JSONResponse:
    """
    Centralized exception handling utility
    
    Args:
        e (Exception): Caught exception
        status_code (int): HTTP status code
    
    Returns:
        JSONResponse with error details
    """
    logger.error(f"Error: {e}")
    logger.error(traceback.format_exc())

    return JSONResponse(
        status_code=status_code, content={"status": "error", "message": str(e), "details": traceback.format_exc()}
    )


def validate_url(url: str) -> bool:
    """
    Validate URL format
    
    Args:
        url (str): URL to validate
    
    Returns:
        bool: Whether URL is valid
    """
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def validate_file_size(file: UploadFile, max_size: int = 50 * 1024 * 1024) -> bool:
    """
    Validate file size
    
    Args:
        file (UploadFile): Uploaded file
        max_size (int): Maximum file size in bytes
    
    Returns:
        bool: Whether file size is acceptable
    """
    return file.size <= max_size if hasattr(file, 'size') else True


def get_file_type(filename: str) -> str:
    """
    Determine file type by extension
    
    Args:
        filename (str): Filename to check
    
    Returns:
        str: File type
    """
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        return mime_type.split('/')[0]
    return 'unknown'


# Pydantic Models
class StorageCreate(BaseModel):
    name: str
    description: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Storage name must be at least 2 characters long')
        return v.strip()


class StorageUpdate(BaseModel):
    name: str
    description: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Storage name must be at least 2 characters long')
        return v.strip()


class ChatCreate(BaseModel):
    name: str
    model_id: Optional[int] = None


class ChatHistoryCreate(BaseModel):
    chat_id: int
    text: str
    author: Literal['user', 'model']


# ChromaDB Client
chroma_client = chromadb.HttpClient(host='localhost', port=8027)

# FastAPI App
app = FastAPI()

# CORS Configuration
origins = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8027"]

app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], )


# Async RAG Query Function
async def query_simple_rag_stream(query: str, collection_name: str, chat_id: int):
    try:
        results = semantic_search(query, collection_name)

        context_text = "\n\n---\n\n".join(results['documents'][0])
        sources = list(set([i.get("url", "pdf source") for i in results['metadatas'][0]]))

        history = []
        for i in get_last_n_messages(chat_id, 5):
            history.append(
                HumanMessage(i['text']) if i['author'] == 'user' else AIMessage(i['text'])
            )

        system_message_content = prompt_template.format(
            context=context_text, question=query
        )
        prompt = [SystemMessage(system_message_content)] + history

        response_stream = model.astream(prompt)
        return response_stream, sources

    except Exception as e:
        logger.error(f"RAG Query Error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error processing RAG query: {str(e)}"
        )


# Root Endpoint
@app.get('/')
async def root():
    return PlainTextResponse("Window of Knowledge Backend")


# File Upload Endpoint
@app.post("/storages/{storage_id}/files", response_model=Dict[str, Any])
async def upload_file(storage_id: int, file: UploadFile = File(...), description: Optional[str] = Form(None)):
    """
    Upload file to storage with comprehensive validation and error handling
    
    Args:
        storage_id (int): Storage ID
        file (UploadFile): File to upload
        description (Optional[str]): File description
    
    Returns:
        JSONResponse with file information
    """
    try:
        # Validate storage
        storage = get_storage_by_id(storage_id)

        # Validate file
        if not validate_file_size(file):
            raise ValueError("File exceeds maximum size of 50MB")

        # Create storage-specific upload directory
        upload_dir = os.path.join(os.getcwd(), 'uploads', str(storage_id))
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"
        local_path = os.path.join(upload_dir, safe_filename)

        # Save file
        async with aiofiles.open(local_path, 'wb') as f:
            content = await file.read()
            await f.write(content)

        # Determine file type
        file_type = get_file_type(file.filename)

        # Save to database
        file_info = save_file(
            storage_id=storage_id, 
            filename=file.filename, 
            local_path=local_path, 
            file_type=file_type,
            source='upload',
            description=description
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"status": "success", "message": "File uploaded successfully", "file": file_info}
        )

    except Exception as e:
        return handle_exception(e)


# URL Addition Endpoint
@app.post("/add-url")
async def add_url_endpoint(request: Request):
    try:
        data = await request.json()
        url = data.get("url")

        # Validate inputs
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="URL is required"
            )

        if not validate_url(url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid URL format"
            )

        add_into_collection(url, "test")
        return JSONResponse(
            content={"status": "success", "message": "Data added successfully"}
        )

    except Exception as e:
        return handle_exception(e)


# Storage Creation Endpoint
@app.post("/storages")
async def create_storage_endpoint(storage: StorageCreate):
    try:
        result = create_storage(storage.name, storage.description)
        return JSONResponse(
            content={"status": "success", "data": result}
        )
    except Exception as e:
        return handle_exception(e)


# Storage Update Endpoint
@app.put("/storages/{storage_id}")
async def update_storage_endpoint(storage_id: int, storage_data: StorageUpdate):
    """
    Update storage name and description
    
    Args:
        storage_id: int - ID of storage to update
        storage_data (StorageUpdate):
            - name: str
            - description: str (optional)
    
    Returns:
        Updated storage record
    """
    try:
        return update_storage(
            storage_id=storage_id, name=storage_data.name, description=storage_data.description
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# Chatting Endpoint
@app.get('/chatting')
async def chat_endpoint(request: Request):
    try:
        data = await request.json()
        query = data.get('query')
        collection_name = data.get('collection_name', 'test')
        chat_id = data.get('chat_id')

        response_stream, sources = await query_simple_rag_stream(query, collection_name, chat_id)

        async def event_generator():
            # First, send the sources as a JSON event
            yield f"data: {json.dumps({'sources': sources})}\n\n"
            # Now, send the response content as events
            async for chunk in response_stream:
                yield f"data: {json.dumps({'content': chunk})}\n\n"

        return StreamingResponse(event_generator(), media_type='text/event-stream')

    except Exception as e:
        return handle_exception(e)


# Chatting V2 Endpoint
@app.post('/chatting_v2')
async def chat_endpoint_v2(request: Request):
    try:
        data = await request.json()
        query = data.get('query')
        collection_name = data.get('collection_name', 'test')
        chat_id = data.get('chat_id')

        response_stream, sources = await query_simple_rag_stream(query, collection_name, chat_id)

        async def event_generator():
            # First, send the sources as a JSON event
            yield f"data: {json.dumps({'sources': sources})}\n\n"
            # Now, send the response content as events
            async for chunk in response_stream:
                yield f"data: {json.dumps({'content': chunk})}\n\n"

        return StreamingResponse(event_generator(), media_type='text/event-stream')

    except Exception as e:
        return handle_exception(e)


# List Storages Endpoint
@app.get("/list_storages")
async def list_storages_endpoint():
    try:
        result = list_storages()
        return JSONResponse(
            content={"status": "success", "data": result}
        )
    except Exception as e:
        return handle_exception(e)


# Check Records Endpoint
@app.get("/check-records")
async def check_records_endpoint():
    try:
        result = check_existing_records()
        return JSONResponse(
            content={"status": "success", "data": result}
        )
    except Exception as e:
        return handle_exception(e)


# List Storage Files Endpoint
@app.get("/storages/{storage_id}/files")
async def list_storage_files(storage_id: int):
    """
    Get list of files in storage
    
    Args:
        storage_id: int - ID of storage to get files from
    
    Returns:
        List of files in storage
    """
    try:
        return get_storage_files(storage_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# Get File Info Endpoint
@app.get("/storages/{storage_id}/files/{file_id}")
async def get_file_info(storage_id: int, file_id: int):
    """
    Get detailed information about a specific file
    
    Args:
        storage_id: int - ID of storage
        file_id: int - ID of file
    
    Returns:
        File information including metadata
    """
    try:
        return get_file_details(storage_id, file_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# List Chats Endpoint
@app.get("/chats")
async def list_chats():
    """
    Retrieve all chats, ordered by most recently updated.
    
    Returns:
        List of chat records
    """
    return get_chats()


# Create Chat Endpoint
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
        name=chat_data.name, model_id=chat_data.model_id
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
        chat_id=chat_history.chat_id, text=chat_history.text, author=chat_history.author
    )


@app.get("/models")
async def get_models():
    """
    Retrieve all available models.
    
    Returns:
        List of model records
    """
    return list_models()


@app.delete("/storages/{storage_id}/files/{file_id}")
async def delete_file(storage_id: int, file_id: int):
    """
    Delete file from storage
    
    Args:
        storage_id: int - ID of storage
        file_id: int - ID of file
        
    Returns:
        Success status
    """
    try:
        local_path = delete_storage_file(storage_id, file_id)

        # Delete physical file if it exists
        if os.path.exists(local_path):
            os.remove(local_path)

        return JSONResponse(
            content={"status": "success", "message": "File deleted"}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# Update File Metadata Endpoint
@app.patch("/storages/{storage_id}/files/{file_id}")
async def update_file_metadata(storage_id: int, file_id: int, metadata: dict = Body(
    ..., example={"name": "new_name.pdf", "description": "Updated description"}
    )):
    """
    Update file metadata
    
    Args:
        storage_id: int - ID of storage
        file_id: int - ID of file
        metadata: dict with fields to update
        
    Returns:
        Updated file information
    """
    try:
        result = update_file_info(storage_id, file_id, metadata)
        return JSONResponse(
            content={"status": "success", "data": result}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# Add PDF validation function
def validate_pdf(file: UploadFile) -> bool:
    """
    Validate if file is a PDF
    
    Args:
        file (UploadFile): File to validate
        
    Returns:
        bool: Whether file is a valid PDF
    """
    # Check content type
    if file.content_type != "application/pdf":
        return False
    
    # Check file extension
    return file.filename.lower().endswith('.pdf')


# Modify the existing upload endpoint or add a new one specifically for PDFs
@app.post("/upload-pdf")
async def upload_pdf(
    storage_id: int, 
    file: UploadFile = File(...),
    description: Optional[str] = Form(None)
):
    """
    Upload PDF file to storage
    
    Args:
        storage_id (int): Storage ID
        file (UploadFile): PDF file to upload
        description (Optional[str]): File description
    
    Returns:
        JSONResponse with file information
    """
    try:
        # Validate storage
        storage = get_storage_by_id(storage_id)

        # Validate PDF format
        if not validate_pdf(file):
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Only PDF files are allowed."
            )

        # Validate file size (50MB limit)
        if not validate_file_size(file):
            raise HTTPException(
                status_code=400,
                detail="File exceeds maximum size of 50MB"
            )

        # Create storage-specific upload directory
        upload_dir = os.path.join(os.getcwd(), 'uploads', str(storage_id))
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"
        local_path = os.path.join(upload_dir, safe_filename)

        # Save file
        async with aiofiles.open(local_path, 'wb') as f:
            content = await file.read()
            await f.write(content)

        # Process PDF for vector storage
        try:
            add_into_collection(local_path, f"test")
        except Exception as e:
            logger.error(f"Error processing PDF for vector storage: {e}")
            # Continue even if vector processing fails
            # You may want to add a status flag in the response

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "status": "success",
                "message": "PDF uploaded and processed successfully"
            }
        )

    except Exception as e:
        # Clean up file if saved but processing failed
        if 'local_path' in locals() and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except:
                pass
        return handle_exception(e)


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='localhost', port=8040)
