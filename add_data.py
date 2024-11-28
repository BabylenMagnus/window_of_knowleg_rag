import os

# Disable ChromaDB telemetry
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

import chromadb
from datetime import datetime
from utils import url2text
from late_chunking import process_large_text
import fitz  # PyMuPDF for PDF handling

chroma_client = chromadb.HttpClient(host='localhost', port=8027)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file."""
    text = ""
    with fitz.open(pdf_path) as pdf_document:
        for page in pdf_document:
            text += page.get_text()
    return text


def add_into_collection(data: str, collection_name: str):
    collection = chroma_client.get_or_create_collection(name=collection_name)

    metadata = {"created_at": datetime.now().isoformat()}

    if data.startswith("http"):
        text = url2text(data)
        metadata['url'] = data
    elif data.endswith(".pdf"):
        text = extract_text_from_pdf(data)
        metadata['pdf_path'] = data
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
    urls = """
https://journal.tinkoff.ru/football-rules/
https://www.sportmaster.ru/media/articles/26398684/
https://yandex.ru/q/question/skolko_po_vremeni_dlitsia_futbolnyi_match_df7390b4/

https://web.archive.org/web/20120505015830/http://ru.wikipedia.org/wiki/Футбол

https://ru.wikipedia.org/wiki/Вратарь_(футбол)

https://www.sportmaster.ru/media/articles/32086206/

https://kartaslov.ru/значение-слова/вратарь

https://journal.tinkoff.ru/red-cards-football/

https://ru.wikipedia.org/wiki/Красная_карточка

https://translated.turbopages.org/proxy_u/en-ru.ru.eeb2ca27-6748226d-48e44fb5-74722d776562/https/www.geeksforgeeks.org/what-is-red-card-in-football/
"""
    urls = [i for i in urls.split("\n") if len(i)]
    collection = chroma_client.get_or_create_collection("test")
    print("start with ", collection.count())
    for i in urls:
        add_into_collection(i, "test")

    # Example of adding a PDF file
    pdf_file_path = "path/to/your/document.pdf"  # Replace with your PDF file path
    add_into_collection(pdf_file_path, "test")

    print("end with ", collection.count())