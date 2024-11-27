import os
# Disable ChromaDB telemetry
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

import json
import chromadb
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine import model, prompt_template, semantic_search
from add_data import add_into_collection
from db import create_storage, list_storages, check_storage_nickname_exists, check_existing_records


chroma_client = chromadb.HttpClient(host='localhost', port=8027)


# Модели данных
class StorageCreate(BaseModel):
    name: str
    description: str = None


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


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='localhost', port=8040)
