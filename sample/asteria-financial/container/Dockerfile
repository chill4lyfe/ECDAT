FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl libssl-dev && rm -rf /var/lib/apt/lists/*
COPY services/payments /app
