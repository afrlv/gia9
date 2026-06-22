FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/main.py .

RUN mkdir -p /data

ENV STATE_FILE=/data/state.json
ENV CHECK_INTERVAL_SECONDS=300

CMD ["python", "-u", "main.py"]
