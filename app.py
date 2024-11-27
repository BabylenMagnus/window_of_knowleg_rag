import json
import chromadb
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from engine import model, prompt_template, semantic_search

chroma_client = chromadb.HttpClient(host='localhost', port=8027)


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
origins = ["http://localhost:5173",  # Ваш фронтенд
    # Добавьте другие origin, если необходимо
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешает запросы с любого домена
    allow_credentials=True,
    allow_methods=["*"],  # Разрешает все HTTP методы: GET, POST, OPTIONS и т.д.
    allow_headers=["*"],  # Разрешает все заголовки: Content-Type, Authorization и т.д.
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


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='localhost', port=8040)
