# BigQuery AI Toolbox CLI

Isolated CLI package for the BigQuery Toolbox.

## Features
- **Chat & Query**: Interact with the backend engine via WebSockets.
- **Ingestion**: Ingest files from a local directory.
- **Service Discovery**: Uses Ray (if available) to interpret Backend URLs.
- **Authentication**: Secure interaction requiring email/password.

## Setup

### 1. Build Docker Image
```bash
docker build -t bq-toolbox-cli .
```

### 2. Run
```bash
docker run -it --rm \
  -e DOMAIN="your-backend-domain.com" \
  -e CLI_EMAIL="user@example.com" \
  -e CLI_PASSWORD="password" \
  -v /path/to/your/data:/app/data_dir \
  bq-toolbox-cli
```

## Service Discovery (Ray)
The CLI acts as a client. If it can connect to a Ray cluster (e.g. via `ray.init(address='auto')` if running in a matching environment), it will query the actor named `bq_agent` for the list of service URLs. 
Otherwise, it falls back to `{DOMAIN}/ws/chat/`.
