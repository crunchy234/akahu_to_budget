ARG BUILD_FROM=python:3.12-alpine
FROM $BUILD_FROM

WORKDIR /app/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules ./modules
COPY flask_app.py .
COPY sync_cli.py .

RUN apk add --no-cache jq bash

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
