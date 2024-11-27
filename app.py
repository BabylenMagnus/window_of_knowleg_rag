import json
import chromadb
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, PlainTextResponse

from engine import model, prompt_template, semantic_search


# Initialize ChromaDB client
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


@app.get('/')
async def root():
    return PlainTextResponse("Здараво бандины")  # Возвращаем текст при обращении к корневому пути


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


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='localhost', port=8040)
