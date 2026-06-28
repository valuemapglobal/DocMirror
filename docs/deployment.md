# Deployment Guide

Deploying DocMirror in a production environment.

## Docker Deployment

```bash
# Build
docker build -t docmirror:latest .

# Run
docker run -d \
  --name docmirror \
  -p 8000:8000 \
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
| `DOCMIRROR_WORKERS` | `4` | Worker pool size |
| `DOCMIRROR_CACHE_TTL` | `3600` | Cache TTL in seconds (requires Redis) |
| `DOCMIRROR_REDIS_URL` | — | Redis connection string for caching |
| `DOCMIRROR_LICENSE` | — | Online license key |
| `DOCMIRROR_REQUEST_SIZE_MB` | `50` | Max upload file size in MB |

### Docker Compose

```yaml
version: "3.8"
services:
  docmirror:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ~/.docmirror:/root/.docmirror
    environment:
      - DOCMIRROR_API_KEY=${DOCMIRROR_API_KEY}
      - DOCMIRROR_LOG_LEVEL=info
    deploy:
      resources:
        limits:
          memory: 2G
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

- Set `DOCMIRROR_WORKERS` to the number of CPU cores
- For OCR-heavy workloads, consider 2x CPU cores

### Memory

- 2 GB minimum for production
- 4 GB recommended for documents with OCR
- 8 GB for documents with 200+ pages

### Cache

Enable Redis caching for repeated document parsing:

```bash
docker run -d --name redis redis:alpine
export DOCMIRROR_REDIS_URL=redis://redis:6379/0
```
