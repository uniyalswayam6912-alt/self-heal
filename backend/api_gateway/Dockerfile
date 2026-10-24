FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/api_gateway/ ./backend/api_gateway/

EXPOSE 8000

CMD ["uvicorn", "backend.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
