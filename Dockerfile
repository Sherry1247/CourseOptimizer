# BadgerPlan public deployment (Render, Fly.io, Railway or any Docker host).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BADGERPLAN_PUBLIC=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Build the SQLite catalog from the committed snapshot (about 2 seconds).
RUN python scripts/init_db.py --force

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"
CMD ["sh", "-c", "uvicorn web_app:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
