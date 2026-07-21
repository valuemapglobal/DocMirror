"""DocMirror Python SDK — product-grade client surface.

``DocMirrorClient`` is the synchronous entry point for one-shot parsing.
``AsyncDocMirrorClient`` provides the same API surface for async/await users.

Both clients delegate to the shared ``perceive_document()`` engine and
return stable ``TaskResult`` objects with artifacts, errors, and observability
context.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from docmirror.input.entry.factory import PerceiveOptions, perceive_document
from docmirror.input.entry.options import normalize_parse_policy
from docmirror.sdk.integration.errors import ErrorEnvelope
from docmirror.sdk.integration.observability import build_observability_context
from docmirror.server.edition_outputs import write_outputs
from docmirror.server.task_result import TaskResult, task_result_from_manifest

logger = logging.getLogger(__name__)


def _resolve_path(path_or_str: str | Path) -> Path:
    """Coerce input to an absolute resolved Path."""
    p = Path(path_or_str)
    return p.resolve()


def _run_async(coro):
    """Run async coroutine in the current event-loop or a new one."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


# ── Async task helper ──


async def parse_to_task(
    file_path: str | Path,
    output_dir: str | Path = "output",
    *,
    options: PerceiveOptions | None = None,
) -> TaskResult:
    """One-shot async parse that writes artifacts and returns a ``TaskResult``."""
    result = await perceive_document(file_path, options or PerceiveOptions())
    task_id, _written = write_outputs(
        result,
        Path(output_dir),
        file_path=str(file_path),
    )
    return task_result_from_manifest(Path(output_dir) / task_id / "manifest.json")


class DocMirrorClient:
    """Synchronous DocMirror parse client.

    Usage::

        client = DocMirrorClient()
        task = client.parse("sample.pdf")
        chunks = client.load_chunks(task)
    """

    def __init__(self, output_dir: str | Path = "output"):
        self.output_dir = Path(output_dir).resolve()

    def parse(
        self,
        file_path: str | Path,
        *,
        mode: str = "auto",
        pages: str | None = None,
        doc_type: str | None = None,
        ocr_correction: str = "safe",
        ocr_language: str | None = None,
        ocr_country: str | None = None,
        ocr_locale: str | None = None,
        ocr_correction_packs: list[str] | None = None,
        raise_on_error: bool = False,
    ) -> TaskResult:
        """Parse a single document synchronously.

        Args:
            file_path: Path to the document.
            mode: Parse mode — ``auto``, ``fast``, ``balanced``, ``accurate``, ``forensic``.
            pages: Page selection string.
            doc_type: Document type hint.
            ocr_correction: Deterministic OCR correction policy — ``safe``, ``suggest``, or ``off``.
            ocr_language: Optional ISO 639 language hint for correction pack selection.
            ocr_country: Optional ISO country hint for validators and correction packs.
            ocr_locale: Optional locale hint such as ``zh-CN``.
            ocr_correction_packs: Optional correction pack ids to enable.
            raise_on_error: If True, raise ``DocMirrorError`` on failure.

        Returns:
            TaskResult with task_id, status, artifacts, errors, and observability.
        """
        return _run_async(
            self._parse_async(
                file_path,
                mode=mode,
                pages=pages,
                doc_type=doc_type,
                ocr_correction=ocr_correction,
                ocr_language=ocr_language,
                ocr_country=ocr_country,
                ocr_locale=ocr_locale,
                ocr_correction_packs=ocr_correction_packs,
                raise_on_error=raise_on_error,
            )
        )

    async def _parse_async(
        self,
        file_path: str | Path,
        *,
        mode: str = "auto",
        pages: str | None = None,
        doc_type: str | None = None,
        ocr_correction: str = "safe",
        ocr_language: str | None = None,
        ocr_country: str | None = None,
        ocr_locale: str | None = None,
        ocr_correction_packs: list[str] | None = None,
        raise_on_error: bool = False,
    ) -> TaskResult:
        """Async implementation of parse()."""
        path = _resolve_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        obs = build_observability_context(profile="fixed", entry="sdk")
        request_id = obs.request_id
        policy = normalize_parse_policy(
            mode=mode,
            pages=pages,
            doc_type_hint=doc_type,
            ocr_correction=ocr_correction,
            ocr_language=ocr_language,
            ocr_country=ocr_country,
            ocr_locale=ocr_locale,
            ocr_correction_packs=ocr_correction_packs,
        )
        options = PerceiveOptions(policy=policy)

        try:
            result = await perceive_document(path, options)
        except Exception as exc:
            envelope = ErrorEnvelope.from_exception(exc, request_id=request_id)
            if raise_on_error:
                raise DocMirrorError(envelope) from exc
            return TaskResult(
                task_id=f"error_{request_id}",
                status="failed",
                inputs=[{"file_path": str(path)}],
                errors=[envelope.to_dict()],
            )

        task_id, written = write_outputs(
            result,
            self.output_dir,
            file_path=str(path),
        )

        manifest_path = self.output_dir / task_id / "manifest.json"
        if manifest_path.is_file():
            task = task_result_from_manifest(manifest_path)
        else:
            task = TaskResult(
                task_id=task_id,
                status="success",
                inputs=[{"file_path": str(path)}],
                artifacts={k: v.name if isinstance(v, Path) else v for k, v in written.items() if v},
            )

        # Inject observability into the result
        task_dict = task.model_dump()
        task_dict.setdefault("observability", obs.to_dict())
        task_dict["request_id"] = request_id
        return TaskResult(**{k: v for k, v in task_dict.items() if k in TaskResult.model_fields})

    def load_chunks(self, task: TaskResult) -> list[dict[str, Any]]:
        """Load RAG chunks from a completed task's artifacts."""
        chunks_name = task.artifacts.get("chunks")
        if not chunks_name:
            # Try to load from the task directory
            task_dir = self.output_dir / task.task_id
            chunks_path = task_dir / "006_chunks.json"
            if not chunks_path.is_file():
                return []
        else:
            chunks_path = self.output_dir / task.task_id / chunks_name

        if not chunks_path.is_file():
            return []

        data = json.loads(chunks_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("chunks", [])

    def wait_task(self, task_id: str, *, timeout_s: float = 300) -> TaskResult:
        """Poll task until complete.

        Note: Local-mode only. For REST tasks, use the REST wrapper.
        """
        return _run_async(self._wait_async(task_id, timeout_s=timeout_s))

    async def _wait_async(self, task_id: str, *, timeout_s: float = 300) -> TaskResult:
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            manifest_path = self.output_dir / task_id / "manifest.json"
            if manifest_path.is_file():
                task = task_result_from_manifest(manifest_path)
                if task.status in ("success", "partial", "failed"):
                    return task
            elapsed = loop.time() - start
            if elapsed > timeout_s:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout_s}s")
            await asyncio.sleep(1.0)


class AsyncDocMirrorClient:
    """Asynchronous DocMirror parse client — same API surface as ``DocMirrorClient``.

    Usage::

        async with AsyncDocMirrorClient() as client:
            task = await client.parse("sample.pdf")
    """

    def __init__(self, output_dir: str | Path = "output"):
        self._sync = DocMirrorClient(output_dir=output_dir)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def parse(
        self,
        file_path: str | Path,
        *,
        mode: str = "auto",
        pages: str | None = None,
        doc_type: str | None = None,
        raise_on_error: bool = False,
    ) -> TaskResult:
        return await self._sync._parse_async(
            file_path,
            mode=mode,
            pages=pages,
            doc_type=doc_type,
            raise_on_error=raise_on_error,
        )

    async def load_chunks(self, task: TaskResult) -> list[dict[str, Any]]:
        return self._sync.load_chunks(task)

    async def wait_task(self, task_id: str, *, timeout_s: float = 300) -> TaskResult:
        return await self._sync._wait_async(task_id, timeout_s=timeout_s)


class DocMirrorError(Exception):
    """Raised when ``raise_on_error=True`` and a parse fails.

    Attributes:
        envelope: The stable ``ErrorEnvelope`` from the failed parse.
    """

    def __init__(self, envelope: ErrorEnvelope):
        self.envelope = envelope
        super().__init__(f"[{envelope.code}] {envelope.message}")
