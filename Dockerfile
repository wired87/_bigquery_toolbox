FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    python3-pyaudio \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure channels/daphne/django are installed (if requirements.txt wasn't updated in source context correctly)
RUN pip install django channels daphne djangorestframework

COPY . .

EXPOSE 8080

ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
ENV DJANGO_SETTINGS_MODULE=config.settings

# Collect static if needed? Not for API usually.
# RUN python manage.py collectstatic --noinput

CMD ["daphne", "-b", "0.0.0.0", "-p", "8080", "config.asgi:application"]
