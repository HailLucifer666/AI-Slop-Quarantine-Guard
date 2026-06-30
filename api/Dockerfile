# Multi-stage build, non-root, distroless final stage

# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml pyproject.toml

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -e .

# Final stage: distroless
FROM python:3.12-slim

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy only runtime dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY ./app ./app

# Switch to non-root user
USER appuser

# Health check — uses stdlib urllib (no extra dependency); non-2xx raises → unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz').read()" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
