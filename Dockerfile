FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y rsync openssh-client gosu && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ms78_api.py .
COPY make_icons.py .
COPY entrypoint.sh .
COPY templates/ templates/
COPY www/ www/

RUN python3 make_icons.py && chmod +x entrypoint.sh

ENV VAULT_PATH=/data/caderno
ENV MS78_API_TOKEN=muda_este_token
ENV SYNC_TARGET=

EXPOSE 8787

CMD ["./entrypoint.sh"]
