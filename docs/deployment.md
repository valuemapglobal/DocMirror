# Deployment Guide

Deploy DocMirror as a local HTTP service for API integrations and internal
evaluation.

The primary integration endpoint is `POST /v1/tasks`. Send either multipart
`file` or repeated `files` fields. Add `wait=true` for a synchronous response;
otherwise poll `GET /v1/tasks/{task_id}`. Both paths return the same compact
`TaskResult`, never Mirror JSON. Download outputs by stable role from
`/v1/tasks/{task_id}/files/{file_id}/artifacts/{role}`.

## Docker Deployment

```bash
# Build
docker build -t docmirror:latest .

# Run
docker run -d \
  --name docmirror \
  -p 8000:8000 \
  -v ~/.cache/docmirror:/root/.cache \
  -v ~/.docmirror:/root/.docmirror \
  --restart unless-stopped \
  docmirror:latest
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCMIRROR_API_KEY` | — | API key for request authentication |
| `DOCMIRROR_LOG_LEVEL` | `info` | Logging level |
| `DOCMIRROR_MAX_PAGES` | `200` | Maximum pages to process per document |
| `DOCMIRROR_LICENSE` | — | Optional commercial license key |
| `OMP_NUM_THREADS` | — | Optional native thread limit for OCR/math libraries |

### Docker Compose

```yaml
version: "3.8"
services:
  docmirror:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - docmirror_cache:/root/.cache
      - docmirror_data:/root/.docmirror
    environment:
      - DOCMIRROR_API_KEY=${DOCMIRROR_API_KEY}
      - DOCMIRROR_LOG_LEVEL=info
      - OMP_NUM_THREADS=4
    deploy:
      resources:
        limits:
          memory: 2G

volumes:
  docmirror_cache:
  docmirror_data:
```

## Reverse Proxy

### Nginx

```nginx
server {
    listen 443 ssl;
    server_name docmirror.example.com;

    ssl_certificate /etc/ssl/certs/docmirror.crt;
    ssl_certificate_key /etc/ssl/private/docmirror.key;

    client_max_body_size 100M;
    proxy_read_timeout 120s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Caddy

```caddyfile
docmirror.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Performance Tuning

### CPU

- Set `OMP_NUM_THREADS` to avoid native OCR/math libraries overusing CPU cores.
- For OCR-heavy workloads, start conservatively and raise the thread limit after measuring latency and memory.

### Memory

- 2 GB minimum for production
- 4 GB recommended for documents with OCR
- 8 GB for documents with 200+ pages
