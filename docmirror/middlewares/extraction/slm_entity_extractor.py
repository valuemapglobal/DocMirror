import time
import os
import re
import json
import logging
import threading
import concurrent.futures

logger = logging.getLogger(__name__)

from docmirror.middlewares.base import BaseMiddleware
from docmirror.models.entities.parse_result import ParseResult, ResultStatus


class SLMEntityExtractor(BaseMiddleware):
    """
    Industrial-Grade SLM Middleware: Local CPU-based semantic KV extraction.

    Architecture:
        P0: Singleton model cache (class-level lazy init)
        P1: Template-guided fill-value extraction (cognitive downgrade)
        P2: Semantic chunk boundaries (newline-snapping)
        P3: System prompt KV-Cache reuse (consistent message ordering)
        +  Adaptive token budget, JSON repair, robust anchoring
    """

    # ═══════════════════════════════════════════════════════════════
    # P0: Class-level Singleton Model Cache
    # ═══════════════════════════════════════════════════════════════
    _llm_instance = None
    _llm_lock = threading.Lock()

    @classmethod
    def _get_llm(cls):
        """Thread-safe lazy singleton for the LLM instance."""
        if cls._llm_instance is not None:
            return cls._llm_instance
        with cls._llm_lock:
            if cls._llm_instance is not None:
                return cls._llm_instance  # Double-check after lock
            from llama_cpp import Llama
            from huggingface_hub import hf_hub_download

            logger.info("[SLM] Loading Qwen2.5-0.5B-GGUF for local inference (CPU)")
            _t = time.perf_counter()
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            model_path = hf_hub_download(
                repo_id="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                filename="qwen2.5-0.5b-instruct-q8_0.gguf"
            )
            cls._llm_instance = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=os.cpu_count(),
                verbose=False
            )
            logger.info(f"[SLM] Model loaded in {(time.perf_counter()-_t)*1000:.0f}ms")
            return cls._llm_instance

    # ═══════════════════════════════════════════════════════════════
    # JSON Repair Engine
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def _repair_json(text: str) -> dict:
        """Deterministic JSON repair: bracket-counting + force-close."""
        text = text.strip()
        if text.endswith('```'): text = text[:-3].strip()
        first_brace = text.find('{')
        if first_brace == -1: return {}
        text = text[first_brace:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Bracket counting repair
        open_braces = 0
        open_brackets = 0
        in_string = False
        escape_next = False
        last_valid = 0
        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{': open_braces += 1
            elif ch == '}': open_braces -= 1
            elif ch == '[': open_brackets += 1
            elif ch == ']': open_brackets -= 1
            if open_braces >= 0 and open_brackets >= 0:
                last_valid = i
        repaired = text[:last_valid + 1]
        if repaired.count('"') % 2 != 0:
            repaired += '"'
        ob = repaired.count('{') - repaired.count('}')
        osq = repaired.count('[') - repaired.count(']')
        repaired += ']' * max(0, osq)
        repaired += '}' * max(0, ob)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', text)
            return dict(pairs) if pairs else {}

    # ═══════════════════════════════════════════════════════════════
    # P1: Key Candidate Inference (Cognitive Downgrade)
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def _infer_key_candidates(chunk_text: str) -> list[str]:
        """
        Auto-infer key candidates from structured text patterns.
        Filters out section titles (lines starting with （/( or numbered prefixes).
        """
        candidates = []
        
        # Pattern 1: Chinese label followed by colon/equals
        for m in re.finditer(r'([\u4e00-\u9fff]{2,8})[：:＝=]', chunk_text):
            candidates.append(m.group(1))
        
        # Pattern 2: Lines that are pure Chinese labels (2-8 chars)
        for line in chunk_text.split('\n'):
            line = line.strip()
            if 2 <= len(line) <= 8 and re.match(r'^[\u4e00-\u9fff]+$', line):
                candidates.append(line)
        
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    # ═══════════════════════════════════════════════════════════════
    # P2: Semantic Chunk Boundaries
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def _semantic_chunk(text: str, chunk_size: int = 1500, overlap: int = 200, max_chunks: int = 3) -> list[str]:
        """Split text into chunks, snapping boundaries to newlines."""
        chunks = []
        idx = 0
        while idx < len(text) and len(chunks) < max_chunks:
            end = min(idx + chunk_size, len(text))
            if end < len(text):
                newline_pos = text.rfind('\n', idx, end)
                if newline_pos > idx:
                    end = newline_pos + 1
            chunks.append(text[idx:end])
            idx = end - overlap if end < len(text) else end
        return chunks

    # ═══════════════════════════════════════════════════════════════
    # Main Pipeline
    # ═══════════════════════════════════════════════════════════════

    def process(self, result: ParseResult) -> ParseResult:
        try:
            from llama_cpp import Llama
            from huggingface_hub import hf_hub_download
        except ImportError:
            logger.warning("[SLM] Please install: pip install llama-cpp-python huggingface-hub")
            return result

        # Collect target sections
        target_sections = []
        if getattr(result, "sections", None):
            for sec in result.sections:
                if sec.get("level") in (2, 3):
                    target_sections.append(sec)
        if not target_sections:
            logger.debug("[SLM] No L2/L3 sections found — skipping SLM extraction")
            return result
        target_sections = target_sections[:8]

        # P0: Get cached model instance (loaded AFTER section check to avoid wasted resources)
        llm = self._get_llm()

        # Build Markdown-aware document text
        doc_text = result._build_full_text() if hasattr(result, "_build_full_text") else (getattr(result, "full_text", "") or "")
        all_extracted = {}

        # Scene Adaptive
        doc_type = getattr(result.entities, "document_type", "unknown")
        scene_map = {
            "credit_report": "征信报告",
            "bank_statement": "银行流水",
            "invoice": "结算单据"
        }
        doc_scene = scene_map.get(doc_type, "专业结构化") if doc_type != "unknown" else "专业结构化"

        # P3: System prompt is IDENTICAL across all chunks → KV-Cache reused
        system_prompt = (
            f"你是一个顶级的「{doc_scene}」数据抽取引擎。\n"
            "1. 输出必须是单一合法的 JSON 字典。\n"
            "2. Key 必须精炼，Value 忠于原文。\n"
            "3. 过滤无意义字符。"
        )

        def _process_section(sec_idx: int, sec: dict) -> tuple[str, dict]:
            title = sec.get("title", "")
            if not title: return title, {}

            start_idx = doc_text.find(title)
            if start_idx == -1: return title, {}

            # Bound by next section
            end_idx = len(doc_text)
            if sec_idx + 1 < len(target_sections):
                next_title = target_sections[sec_idx + 1].get("title", "")
                if next_title:
                    nxt = doc_text.find(next_title, start_idx + len(title))
                    if nxt != -1: end_idx = nxt
            if end_idx - start_idx > 5000: end_idx = start_idx + 5000

            section_text = doc_text[start_idx:end_idx]

            # P2: Semantic chunking with newline-snapping
            chunks = self._semantic_chunk(section_text)

            merged_kv = {}
            for chunk_id, chunk_text in enumerate(chunks):
                # P1: Infer key candidates from text patterns
                key_candidates = self._infer_key_candidates(chunk_text)

                if key_candidates:
                    # Template-guided: LLM only needs to FILL values (cognitive downgrade)
                    template = {k: "?" for k in key_candidates[:15]}
                    user_prompt = (
                        f"区块【{title}】(碎片 {chunk_id+1}/{len(chunks)})\n"
                        f"请根据下方文本填写以下字段的值：\n"
                        f"{json.dumps(template, ensure_ascii=False)}\n"
                        f"###\n{chunk_text}\n###\n"
                    )
                else:
                    # Fallback: open-ended extraction
                    user_prompt = (
                        f"区块【{title}】(碎片 {chunk_id+1}/{len(chunks)})\n"
                        f"请从下方文本中提取 JSON：\n"
                        f"###\n{chunk_text}\n###\n"
                    )

                try:
                    _t_inf = time.perf_counter()
                    adaptive_max_tokens = min(max(300, len(chunk_text) // 2), 1500)
                    response = llm.create_chat_completion(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=adaptive_max_tokens,
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )
                    out_text = response['choices'][0]['message']['content'].strip()
                    parsed = self._repair_json(out_text)
                    parsed = {k: v for k, v in parsed.items() if v != "?" and v != ""} if isinstance(parsed, dict) else {}
                    if parsed:
                        merged_kv.update(parsed)
                    n_keys = len(key_candidates) if key_candidates else 0
                    logger.info(f"[SLM] '{title}' chunk {chunk_id+1} ({adaptive_max_tokens}tok, {n_keys} template keys) → {len(parsed)} KVs in {(time.perf_counter()-_t_inf)*1000:.0f}ms")
                except Exception as e:
                    logger.error(f"[SLM] Failed chunk {chunk_id+1} on {title}: {e}")
                    merged_kv["_partial"] = True

            return title, merged_kv

        # Execute sections (sequential for local llama.cpp, change max_workers for remote APIs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(_process_section, i, sec) for i, sec in enumerate(target_sections)]
            for future in concurrent.futures.as_completed(futures):
                title, parsed_kv = future.result()
                if title and parsed_kv:
                    all_extracted[title] = parsed_kv

        # Robust Anchoring (Reverse Mapping)
        def _enrich_ast_node(node, content_str: str) -> None:
            if not content_str: return
            for section_title, kv_dict in all_extracted.items():
                if not isinstance(kv_dict, dict): continue
                for k, v in kv_dict.items():
                    v_str = str(v).strip() if v else ""
                    if not v_str: continue
                    is_match = False
                    if len(v_str) > 3:
                        is_match = v_str in content_str
                    else:
                        if (v_str in content_str) and (str(k) in content_str):
                            is_match = True
                    if is_match:
                        if getattr(node, "slm_entities", None) is None:
                            node.slm_entities = {}
                        node.slm_entities[k] = v

        for page in result.pages:
            for text_block in page.texts:
                _enrich_ast_node(text_block, text_block.content)
            for table in page.tables:
                for row in table.rows:
                    for cell in row.cells:
                        _enrich_ast_node(cell, cell.text)

        result.entities.domain_specific["slm_extracted"] = all_extracted
        result.record_mutation(
            middleware_name=self.name,
            target_block_id="document",
            field_changed="domain_specific.slm_extracted",
            old_value={},
            new_value=all_extracted,
            reason="Universal SLM extraction across sections"
        )

        return result
