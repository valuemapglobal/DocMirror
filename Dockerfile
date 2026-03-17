# Stage 1: Build & Dependencies
FROM python:3.10-slim AS builder

# Install system build dependencies required for compiling Python packages and OpenCV/ONNX
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files AND source code (required for editable/local wheel builds)
COPY pyproject.toml README.md ./
COPY docmirror/ docmirror/

# Force pip to build wheels for the heavy dependencies locally (if needed)
RUN pip install --upgrade pip
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels \
    ".[all,server]"

# Stage 2: Runtime Environment
FROM python:3.10-slim

# Install runtime C++ libraries required by OpenCV (rapidocr) and ONNX Runtime
# Also install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the pre-built wheels from the builder stage
COPY --from=builder /app/wheels /wheels

# Copy the actual application source code
COPY . .

# Install the application and all its heavy dependencies (PDF, OCR, Layout, Table, Server)
RUN pip install --no-cache-dir --find-links=/wheels ".[all,server]"

# Expose the FastAPI default port
EXPOSE 8000

# Optional: define volume for model caching (speed up rapidocr models download)
VOLUME ["/root/.cache"]

# Healthcheck for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the Uvicorn ASGI server
CMD ["uvicorn", "docmirror.server.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
