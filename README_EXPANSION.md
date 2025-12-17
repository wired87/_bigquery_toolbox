# BigQuery Toolbox Expansion

This update transforms the CLI into a multi-modal AI engine.

## New Features

### 1. Speech Interaction
- **Input**: Speak your queries using your microphone.
- **Output**: Hear the AI's response read aloud.
- **Toggle**: Enable/Disable at startup.

### 2. Advanced File Ingestion
- **Supported Formats**: PDF, CSV, Images (requires extra deps), Text.
- **Hierarchical Chunking**: Splits documents into large "Parent" chunks (context) and small "Child" chunks (search precision).
- **Embeddings**: Automatically generates embeddings for new content.

### 3. Ray Serve Web App
- **WebSocket Endpoint**: `/ws` for real-time streaming.
- **Dockerized**: Ready for deployment.

## Usage

### CLI
```bash
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run CLI
python cli.py
```

### Data Ingestion
Place files in `./data_dir` and run:
```bash
python cli.py ingest
```

### Web App (Docker)
```bash
docker build -t bq-toolbox .
docker run -p 8000:8000 bq-toolbox
```
Then connect to `ws://localhost:8000/ws`.

## Dependencies
- `SpeechRecognition`, `pyttsx3`, `pyaudio` (Speech)
- `langchain`, `langchain-google-vertexai`, `langchain-community` (AI/Files)
- `ray[serve]` (Web App - Linux/Docker recommended)
