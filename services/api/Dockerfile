FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.txt services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt
COPY packages/decision packages/decision
COPY services/api services/api
COPY fixtures fixtures
ENV PYTHONPATH=/app/packages/decision/src:/app/services/api \
    FIXTURES_DIR=/app/fixtures
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
