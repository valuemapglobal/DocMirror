# API Authentication

DocMirror's REST API supports optional API key authentication.

## Enabling Authentication

Set the `DOCMIRROR_API_KEY` environment variable before starting the server:

```bash
export DOCMIRROR_API_KEY=sk-your-secret-key
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

When set, all API endpoints require authentication via the `Authorization` header.

## Making Authenticated Requests

```bash
curl -H "Authorization: Bearer sk-your-secret-key" \
  -F "file=@document.pdf" \
  http://localhost:8000/v1/parse
```

Without the header, requests return `401 Unauthorized`:

```json
{"detail": "Invalid or missing API key"}
```

## Security Recommendations

- Use a **random 32+ character key** (e.g., `openssl rand -hex 32`)
- Rotate keys periodically
- Use HTTPS in production (see [Deployment Guide](deployment.md))
- Keep the API key out of version control; use environment variables or secrets manager
