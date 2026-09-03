# os42-orchestrator — container image for a free-tier cloud web service.
#
# Deliberately minimal: this repo has no DB driver and no build step, just
# a FastAPI app plus a handful of pure-Python deps (see requirements.txt).
# Python 3.12 to match .github/workflows/tests.yml.
#
# Build context is the REPO ROOT, not deploy/cloud/:
#   docker build -f deploy/cloud/Dockerfile -t os42-orchestrator .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code. The test_*.py files and mock_engines.py at the repo root are
# copied too (cheap, and lets you exec the suite in the container if you
# want); nothing runs them at boot.
COPY . .

# Render / Fly / most PaaS inject $PORT. Default to 8050 (the repo's own
# local-dev port from app/main.py) for a plain `docker run`.
ENV PORT=8050
EXPOSE 8050

# No --reload in cloud. Single worker: the app keeps in-process state
# (in-memory registries + the AutonomousScheduler background loop) and has
# no concurrent-writer story, so more than one worker would double-run the
# scheduler and split the state. Scale by rung, not by worker count.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8050} --workers 1"]
