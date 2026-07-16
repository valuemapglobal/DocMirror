# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
DocMirror REST API — FastAPI application and HTTP endpoints.

Exposes document upload and parse routes, health checks, and optional
background task hooks. Uploads are written to a temp path, passed through
``perceive_document()``, and returned as vNext mirror JSON. Multi-edition
structured outputs can be generated through shared ``output_builder`` helpers
when requested.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import shutil
import time
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Body, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from docmirror import __version__
from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_control
from docmirror.server.schemas import ParseResponse
from docmirror.server.task_api import router as task_router

# Load .env from project root
_env_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_env_root / ".env", override=False)

logger = logging.getLogger(__name__)

# ── API Key authentication (set via DOCMIRROR_API_KEY env var) ──
_API_KEY = os.environ.get("DOCMIRROR_API_KEY", "")

app = FastAPI(
    title="DocMirror Universal Parsing API",
    description="High-performance MultiModal document extraction and enhancement engine.",
    version=__version__,
)

app.include_router(task_router)


# ── Startup/shutdown lifecycle ──


@app.on_event("startup")
async def _cleanup_stale_temp_files():
    """Remove temporary files older than 1 hour on startup.

    Prevents disk exhaustion if previous instances crashed without cleanup.
    """
    tmp_dir = gettempdir()
    cutoff = time.time() - 3600  # 1 hour ago
    cleaned = 0
    for tmp_file in glob.glob(os.path.join(tmp_dir, "tmp*")):
        try:
            if os.path.getmtime(tmp_file) < cutoff:
                os.unlink(tmp_file)
                cleaned += 1
        except OSError:
            pass
    if cleaned:
        logger.info(f"[Server] Cleaned {cleaned} stale temp file(s) on startup")


@app.on_event("startup")
async def _warmup_ocr_engine():
    """Pre-load OCR ONNX model on startup to avoid cold-start latency.

    First request otherwise pays ~500ms-2s for model loading.
    """
    try:
        from docmirror.ocr.vision.rapidocr_engine import get_ocr_engine

        engine = get_ocr_engine()
        if engine:
            logger.info("[Server] OCR engine warmed up on startup")
    except Exception as e:
        logger.debug(f"[Server] OCR warmup skipped: {e}")


@app.get("/health", tags=["System"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "version": __version__}


def cleanup_file(filepath: Path):
    """Background task to remove temporary files."""
    try:
        if filepath.exists():
            filepath.unlink()
    except Exception as e:
        logger.error(f"[Server] Failed to cleanup temp file {filepath}: {e}")


def _verify_api_key(authorization: str | None) -> None:
    """Verify API key if DOCMIRROR_API_KEY is configured."""
    if not _API_KEY:
        return  # No key configured — open access
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    # Accept "Bearer <key>" or raw key
    token = authorization.removeprefix("Bearer ").strip()
    if token != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


@app.post("/v1/parse", responses={200: {"model": ParseResponse}}, tags=["Parsing"])
async def parse_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The document file to parse (PDF, PNG, JPEG, DOCX, etc.)"),
    edition: str = Query(
        default="all",
        pattern="^(community|enterprise|finance|all)$",
        description="Output edition: community, enterprise, finance, or all",
    ),
    include_text: bool = Query(default=False, description="Include full markdown text in response"),
    include_geometry: bool = Query(
        default=False, description="Include table/cell geometry using forensic mirror output"
    ),
    pages: str | None = Query(default=None, description="Page ranges, 1-based: 1-3,8,10-"),
    max_pages: int | None = Query(default=None, description="Maximum pages after applying pages"),
    workers: str | None = Query(default=None, description="Total worker budget for this request"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$", description="Parse mode"),
    ocr_correction: str = Query(
        default="safe",
        pattern="^(off|safe|suggest)$",
        description="Deterministic OCR correction policy",
    ),
    ocr_language: str | None = Query(default=None, description="ISO 639 OCR language hint"),
    ocr_country: str | None = Query(default=None, description="ISO country hint"),
    ocr_locale: str | None = Query(default=None, description="OCR locale hint"),
    ocr_correction_packs: str | None = Query(default=None, description="Comma-separated correction pack ids"),
    format: str = Query(default="json", description="Requested output formats for parse control fingerprint"),
    doc_type_hint: str | None = Query(default=None, description="Manual document type hint, optionally type:force"),
    authorization: str | None = Header(default=None),
):
    """
    Parse a document using the core MultiModal engine.
    The file is saved temporarily, processed, and then asynchronously cleaned up.

    Supports multi-edition output via the ``edition`` parameter:
    - ``community`` → community v2.0 schema
    - ``enterprise`` → enterprise v2.0 schema (requires docmirror-enterprise)
    - ``finance`` → finance v3.0 schema (requires docmirror-finance)
    - ``all`` (default) → all available editions
    """
    _verify_api_key(authorization)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided in upload")

    # Create a secure temporary file with the correct extension
    suffix = Path(file.filename).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = Path(temp_file.name)

    # Schedule cleanup
    background_tasks.add_task(cleanup_file, temp_path)

    try:
        from docmirror.server.output_builder import build_api_response

        mirror_level = "forensic" if include_geometry else "standard"
        control = normalize_parse_control(
            pages=pages,
            max_pages=max_pages,
            workers=workers,
            mode=mode,
            formats=format,
            mirror_level=mirror_level,
            include_text=include_text,
            doc_type_hint=doc_type_hint,
            ocr_correction=ocr_correction,
            ocr_language=ocr_language,
            ocr_country=ocr_country,
            ocr_locale=ocr_locale,
            ocr_correction_packs=ocr_correction_packs,
        )
        result = await perceive_document(temp_path, PerceiveOptions(control=control))
        api_payload = build_api_response(
            result,
            edition=edition,
            include_text=include_text,
            mirror_level=control.output.mirror_level,
        )

        return JSONResponse(status_code=200, content=api_payload)

    except Exception as e:
        logger.exception("[Server] Parse failed with uncaught exception")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/parse/batch", tags=["Parsing"])
async def batch_parse(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="Multiple document files to parse"),
    edition: str = Query(default="all", pattern="^(community|enterprise|finance|all)$", description="Output edition"),
    include_geometry: bool = Query(
        default=False, description="Include table/cell geometry using forensic mirror output"
    ),
    pages: str | None = Query(default=None, description="Page ranges, 1-based: 1-3,8,10-"),
    max_pages: int | None = Query(default=None, description="Maximum pages after applying pages"),
    workers: str | None = Query(default=None, description="Total worker budget for this request"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$", description="Parse mode"),
    ocr_correction: str = Query(default="safe", pattern="^(off|safe|suggest)$"),
    ocr_language: str | None = Query(default=None),
    ocr_country: str | None = Query(default=None),
    ocr_locale: str | None = Query(default=None),
    ocr_correction_packs: str | None = Query(default=None),
    doc_type_hint: str | None = Query(default=None, description="Manual document type hint, optionally type:force"),
    authorization: str | None = Header(default=None),
):
    """Batch parse multiple documents concurrently, each with multi-edition output."""
    _verify_api_key(authorization)

    import multiprocessing as _mp
    from dataclasses import replace

    from docmirror.configs.runtime.performance import resolve_worker_budget
    from docmirror.input.entry.options import ResourceControl
    from docmirror.server.output_builder import build_api_response

    _cpu_count = _mp.cpu_count()
    _control = normalize_parse_control(
        pages=pages,
        max_pages=max_pages,
        workers=workers,
        mode=mode,
        mirror_level="forensic" if include_geometry else "standard",
        doc_type_hint=doc_type_hint,
        ocr_correction=ocr_correction,
        ocr_language=ocr_language,
        ocr_country=ocr_country,
        ocr_locale=ocr_locale,
        ocr_correction_packs=ocr_correction_packs,
    )
    _budget = resolve_worker_budget(_control.resource.workers, file_count=len(files), cpu_count=_cpu_count)
    _semaphore = asyncio.Semaphore(_budget.file_workers)
    _per_file_control = replace(
        _control,
        resource=ResourceControl(
            workers=_budget.page_workers_per_file,
            page_executor=_control.resource.page_executor,
        ),
    )

    async def _process_one(f):
        if not f.filename:
            return None
        suffix = Path(f.filename).suffix
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            import shutil as _shutil

            _shutil.copyfileobj(f.file, temp_file)
            temp_path = Path(temp_file.name)
        background_tasks.add_task(cleanup_file, temp_path)

        async with _semaphore:
            try:
                result = await perceive_document(temp_path, PerceiveOptions(control=_per_file_control))
                payload = build_api_response(
                    result,
                    edition=edition,
                    mirror_level=_per_file_control.output.mirror_level,
                )
                payload["file_name"] = f.filename
                return payload
            except Exception as e:
                return {
                    "file_name": f.filename,
                    "error": str(e),
                }

    results = await asyncio.gather(*[_process_one(f) for f in files], return_exceptions=True)
    results = [r for r in results if r is not None]

    return JSONResponse(content={"results": results})


@app.post("/v1/parse/file", tags=["Parsing"])
async def parse_file_on_server(
    file_path: str = Body(..., description="Absolute path to a file on the server"),
    edition: str = Query(default="all", pattern="^(community|enterprise|finance|all)$", description="Output edition"),
    include_text: bool = Query(default=False, description="Include full markdown text in response"),
    include_geometry: bool = Query(
        default=False, description="Include table/cell geometry using forensic mirror output"
    ),
    pages: str | None = Query(default=None, description="Page ranges, 1-based: 1-3,8,10-"),
    max_pages: int | None = Query(default=None, description="Maximum pages after applying pages"),
    workers: str | None = Query(default=None, description="Total worker budget for this request"),
    mode: str = Query(default="auto", pattern="^(auto|fast|balanced|accurate|forensic)$", description="Parse mode"),
    ocr_correction: str = Query(default="safe", pattern="^(off|safe|suggest)$"),
    ocr_language: str | None = Query(default=None),
    ocr_country: str | None = Query(default=None),
    ocr_locale: str | None = Query(default=None),
    ocr_correction_packs: str | None = Query(default=None),
    format: str = Query(default="json", description="Requested output formats for parse control fingerprint"),
    doc_type_hint: str | None = Query(default=None, description="Manual document type hint, optionally type:force"),
    authorization: str | None = Header(default=None),
):
    """Parse a file already present on the server filesystem."""
    _verify_api_key(authorization)

    from docmirror.server.output_builder import build_api_response

    path = Path(file_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")

    try:
        control = normalize_parse_control(
            pages=pages,
            max_pages=max_pages,
            workers=workers,
            mode=mode,
            formats=format,
            mirror_level="forensic" if include_geometry else "standard",
            include_text=include_text,
            doc_type_hint=doc_type_hint,
            ocr_correction=ocr_correction,
            ocr_language=ocr_language,
            ocr_country=ocr_country,
            ocr_locale=ocr_locale,
            ocr_correction_packs=ocr_correction_packs,
        )
        result = await perceive_document(path, PerceiveOptions(control=control))
        api_payload = build_api_response(
            result,
            edition=edition,
            include_text=include_text,
            mirror_level=control.output.mirror_level,
        )
        return JSONResponse(status_code=200, content=api_payload)
    except Exception as e:
        logger.exception("[Server] Parse file failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/v1/export/pdfua",
    tags=["Export"],
    summary="Export document as PDF/UA accessible document",
)
async def export_pdfua_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The document file to convert to accessible PDF"),
    language: str = Query(default="en-US", description="Document language code"),
    title: str | None = Query(default=None, description="Document title (defaults to detected type)"),
    pdfua_version: str = Query(default="UA-1", pattern="^(UA-1|UA-2)$", description="PDF/UA version target"),
    authorization: str | None = Header(default=None),
):
    """
    Parse a document and return a tagged, accessible PDF/UA document.

    Accepts any document format DocMirror supports (PDF, images, DOCX, etc.),
    parses it into structured DMIR, then projects the structure onto a tagged
    PDF/UA-compliant document using PyMuPDF's tagging API.

    Requirements:
    - Requires ``pip install docmirror[pdfua]`` (PyMuPDF >= 1.23.0)
    - The output PDF includes reading order, heading levels, table structure,
      and language metadata suitable for screen reader consumption.

    Returns the tagged PDF as a binary file download.
    """
    _verify_api_key(authorization)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided in upload")

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = Path(temp_file.name)

    background_tasks.add_task(cleanup_file, temp_path)

    try:
        from docmirror.input.entry.factory import PerceiveOptions, perceive_document
        from docmirror.input.entry.options import normalize_parse_control
        from docmirror.output.dmir import serialize_dmir
        from docmirror.output.exporters.pdfua import PdfUaVersion, export_pdfua

        # Parse document
        control = normalize_parse_control(mode="auto")
        result = await perceive_document(temp_path, PerceiveOptions(control=control))

        # Serialize to DMIR
        dmir = serialize_dmir(result)

        # Create output path next to the temp input
        pdf_version = PdfUaVersion.PDFUA_2 if pdfua_version == "UA-2" else PdfUaVersion.PDFUA_1
        output_path = temp_path.with_suffix(".pdfua.pdf")

        # Export to tagged PDF
        export_result = export_pdfua(
            dmir,
            output_path=str(output_path),
            title=title,
            language=language,
            schema_version=pdf_version,
        )

        background_tasks.add_task(cleanup_file, output_path)

        if not export_result.success:
            error_detail = "; ".join(export_result.errors) if export_result.errors else "PDF/UA export failed"
            raise HTTPException(status_code=500, detail=error_detail)

        # Return the tagged PDF as a file download
        media_type = "application/pdf"
        download_name = f"{Path(file.filename).stem}_accessible.pdf"

        return FileResponse(
            path=str(output_path),
            media_type=media_type,
            filename=download_name,
            headers={
                "X-PDFUA-Version": pdfua_version,
                "X-PDFUA-Page-Count": str(export_result.page_count),
            },
        )

    except ImportError as e:
        if "pdfua" in str(e) or "PyMuPDF" in str(e) or "fitz" in str(e):
            raise HTTPException(
                status_code=501,
                detail="PDF/UA export requires docmirror[pdfua] extra: pip install docmirror[pdfua]",
            )
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Server] PDF/UA export failed with uncaught exception")
        raise HTTPException(status_code=500, detail=str(e))
