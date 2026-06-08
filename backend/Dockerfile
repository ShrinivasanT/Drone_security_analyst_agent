FROM python:3.12-slim

WORKDIR /app

# libGL/glib are needed by opencv at import time (pulled in via shared requirements,
# used by data/ in later stages); cheap to add here so the image is forward-compatible.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent ./agent
COPY backend ./backend
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
