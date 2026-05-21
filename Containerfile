FROM python:3.12-alpine

WORKDIR /app/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules ./modules
COPY ["README.md", "LICENSE", "*.py", "."]

RUN adduser -D app && chown -R app:app /app
USER app

EXPOSE 5000

ENTRYPOINT ["python", "sync_cli.py"]
# Default to a one-off sync. Use host cron/systemd timers for scheduled syncs.
