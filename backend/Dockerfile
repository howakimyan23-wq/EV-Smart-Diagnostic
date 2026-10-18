FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FRONTEND_FILE=/srv/frontend.html
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY frontend.html ./frontend.html
RUN useradd --system --uid 10001 --create-home appuser && chown -R appuser:appuser /srv
USER appuser
CMD ["sh","-c","uvicorn app.main:app --host ${UVICORN_HOST:-127.0.0.1} --port 8000"]
