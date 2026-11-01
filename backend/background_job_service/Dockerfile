FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/background_job_service/ ./backend/background_job_service/

COPY migrations/ ./migrations/
COPY alembic.ini .

EXPOSE 8000

CMD ["uvicorn", "backend.background_job_service.main:app", "--host", "0.0.0.0", "--port", "8000"]

