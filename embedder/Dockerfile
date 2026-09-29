FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY embedder.py .
EXPOSE 8500
CMD ["uvicorn", "embedder:app", "--host", "0.0.0.0", "--port", "8500", "--workers", "1"]
