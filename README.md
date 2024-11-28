## Необходимые команды

```
pip install -r requests.txt
```

### Docker
Конфиг находится в docker-compose.yml
```
docker-compose up
```

### ChromaDB
Отключена телеметрия, сохраняется на диск
```
docker run -p 8027:8000 -v Z:\Coding\window_of_knowlege_back\data\chroma\:/chroma/chroma  -e ANONYMIZED_TELEMETRY=False chromadb/chroma
```

Используются подход https://github.com/jina-ai/late-chunking 
Модель ембедингов https://huggingface.co/deepvk/USER-bge-m3

### Ollama

Используется модель `hf.co/mav23/Vikhr-Nemo-12B-Instruct-R-21-09-24-GGUF:Q8_0`

```
ollama serve
```
