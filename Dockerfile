# Dockerfile

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Add src to PYTHONPATH
ENV PYTHONPATH=/app/src:$PYTHONPATH

ENTRYPOINT ["python", "src/run.py"]
