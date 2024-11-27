import chromadb
from late_chunking import embed_model, tokenizer

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM


chroma_client = chromadb.HttpClient(host='localhost', port=8027)

PROMPT_TEMPLATE = """
Answer the question based only on the following context:
{context}
---
Answer the question based on the above context: {question}
"""
prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
model = OllamaLLM(model="hf.co/mav23/Vikhr-Nemo-12B-Instruct-R-21-09-24-GGUF:Q8_0")


def semantic_search(query, collection_name):
    collection = chroma_client.get_or_create_collection(name=collection_name)
    embeds = embed_model(**tokenizer(query, return_tensors='pt'))
    results = collection.query(
        query_embeddings=embeds.pooler_output.detach().cpu().numpy(), n_results=3
    )  # другую функцию поиска надо, и подобрать нижнюю границу схожести
    return results


def query_simple_rag(query, collection_name):
    # Сделать историю / smart context
    # работа с несколькими коллекциями
    # multi hook
    results = semantic_search(query, collection_name)
    context_text = "\n\n---\n\n".join(results['documents'][0])
    sources = list(set([i['url'] for i in results['metadatas'][0]]))
    prompt = prompt_template.format(context=context_text, question=query)
    response_text = model.predict(prompt)
    return response_text, sources


if __name__ == '__main__':
    while True:
        query = input("Вопрос: ")
        response_text, sources = query_simple_rag(query, "test")
        print("Ответ: ", response_text)
        print("Задействованы источники:\n - ", "\n - ".join(sources))
