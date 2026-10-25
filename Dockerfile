# Jatayu server: review API + Fleet dashboard. Build: docker build -t jatayu .
FROM python:3.12-slim

# git: Fleet clones public repos to read their manifests.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY static ./static
RUN uv sync --frozen --no-dev && mkdir -p runs context

RUN useradd --create-home --uid 10001 jatayu && chown -R jatayu /app
USER jatayu

ENV PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
# Secrets come from the platform at runtime (GEMINI_API_KEY, JATAYU_DASHBOARD_TOKEN), never the image.
CMD ["sh", "-c", "uv run --no-sync uvicorn unpinned.server:app --host 0.0.0.0 --port ${PORT}"]
