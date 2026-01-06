FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (PortAudio for speech)
RUN apt-get update && apt-get install -y \
    build-essential \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy data_dir placeholder if needed, or rely on bind mounts
RUN mkdir data_dir

# Copy the module code. 
# Assumes build context is the toolbox_cli directory or we copy specifically.
# To be safe regarding build context, we copy contents to the package dir structure.
COPY . /app/toolbox_cli

# Set PYTHONPATH so 'toolbox_cli' is found
ENV PYTHONPATH=/app

# Default Env Var
ENV DOMAIN="localhost:8000"

ENTRYPOINT ["python", "-m", "toolbox_cli.main"]
