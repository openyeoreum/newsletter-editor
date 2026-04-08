FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY templates /app/templates
COPY MANUAL.md /app/MANUAL.md

ENV PYTHONUNBUFFERED=1 \
    TEMPLATES_DIR=/app/templates \
    DRAFTS_DIR=/data/drafts

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
