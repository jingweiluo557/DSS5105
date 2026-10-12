FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/threadpilot
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
# The discovery and risk engine shared with the morning briefing (standard library only; see backend/app/discovery.py)
COPY simulation/__init__.py simulation/briefing.py simulation/prediction.py simulation/workdays.py ./simulation/
COPY frontend ./frontend
COPY data/dictionary ./data/dictionary
COPY data/migrations ./data/migrations
COPY data/orders.csv data/production_log.csv data/workshops.csv ./data/
RUN mkdir -p backend/runtime data/raw data/snapshots && useradd -m app && chown -R app:app /srv/threadpilot
USER app
WORKDIR /srv/threadpilot/backend
EXPOSE 8000
CMD ["python", "-m", "scripts.serve"]
