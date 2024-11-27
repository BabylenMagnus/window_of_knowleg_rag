import chromadb
from datetime import datetime

from utils import url2text
from late_chunking import process_large_text


chroma_client = chromadb.HttpClient(host='localhost', port=8027)


def add_into_collection(data: str, collection_name: str):
    collection = chroma_client.get_or_create_collection(name=collection_name)

    metadata = {
        "created_at": datetime.now().isoformat()
    }
    if data.startswith("http"):
        text = url2text(data)
        metadata['url'] = data
    else:
        # костыль
        assert False, "Не поддерживаемый формат"

    start = collection.count()
    all_chunks, all_embeddings = process_large_text(text)

    collection.add(
        documents=all_chunks, embeddings=all_embeddings, metadatas=[metadata for _ in all_chunks],
        ids=[str(i) for i in range(start, start + len(all_chunks))]
    )


if __name__ == '__main__':
    urls = [
        "https://www.xtremepush.com/blog/improve-player-experience",
    ]
    collection = chroma_client.get_or_create_collection("test")
    print("start with ", collection.count())
    for i in urls:
        add_into_collection(i, "test")

    print("end with ", collection.count())
