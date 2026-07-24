# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Core classification engine used by the ``docmirror classify`` CLI.

Orchestrates directory traversal, optional lightweight parsing, document-type
matching against the 120-type taxonomy, and physical file organization into
type-specific output folders. Classification uses the Core rule set and parse
pipeline; post-seal plugins do not participate in routing decisions.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from docmirror.layout.scene.rules import RuleManager

logger = logging.getLogger(__name__)


@dataclass
class ClassificationMatch:
    """Classification match result."""

    source: str  # "rule" or "plugin"
    category_id: str
    category_name: str
    target_dir: str
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """Classification result for a single file."""

    source_path: Path
    category: str | None = None
    target_path: Path | None = None
    matches: list[ClassificationMatch] = field(default_factory=list)
    confidence: float = 0.0
    success: bool = False
    error: str | None = None
    is_pending: bool = False  # whether manual review is needed


@dataclass
class ClassificationResults:
    """Collection of classification results."""

    results: list[ClassificationResult] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def total_files(self) -> int:
        """Total number of files."""
        return len(self.results) + len(self.errors)

    @property
    def success_count(self) -> int:
        """Number of successfully classified files."""
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        """Number of failed classifications."""
        return len(self.errors)

    @property
    def unmatched_count(self) -> int:
        """Number of unmatched files."""
        return sum(1 for r in self.results if not r.success and not r.error)

    @property
    def pending_count(self) -> int:
        """Number of pending files."""
        return sum(1 for r in self.results if r.is_pending)

    @property
    def avg_confidence(self) -> float:
        """Average confidence score."""
        successful = [r.confidence for r in self.results if r.success]
        return sum(successful) / len(successful) if successful else 0.0

    def add(self, result: ClassificationResult) -> None:
        """Add a classification result."""
        self.results.append(result)

    def add_error(self, file_path: Path, error: str) -> None:
        """Add an error record."""
        self.errors.append((file_path, error))

    def get_results_by_category(self) -> dict[str, list[ClassificationResult]]:
        """Group results by category."""
        grouped: dict[str, list[ClassificationResult]] = {}
        for result in self.results:
            if result.category:
                if result.category not in grouped:
                    grouped[result.category] = []
                grouped[result.category].append(result)
        return grouped


class FileClassifier:
    """Intelligent File Classifier."""

    def __init__(self, rules_path: Path | None = None, output_dir: Path | None = None, dry_run: bool = False):
        """
        Initialize the classifier.

        Args:
            rules_path: Rule configuration path
            output_dir: Output directory
            dry_run: Preview only (do not move files)
        """
        self.rule_manager = RuleManager(rules_path)
        self.rules = self.rule_manager.get_rules()
        self.output_dir = output_dir or Path.cwd() / "classified_output"
        self.dry_run = dry_run
        self.results = ClassificationResults()

    async def classify_directory(self, source_dir: Path) -> ClassificationResults:
        """
        Traverse a directory and classify all files.

        Args:
            source_dir: Source directory path

        Returns:
            Classification result collection
        """
        import asyncio

        self.results.start_time = datetime.now()
        logger.info(f"[FileClassifier] Starting classification of: {source_dir}")

        # Scan files
        files = self._scan_files(source_dir)
        logger.info(f"[FileClassifier] Found {len(files)} files to classify")

        # Process files in parallel
        tasks = [self._classify_file(file_path) for file_path in files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.results.add_error(files[i], str(result))
                logger.error(f"[FileClassifier] Error classifying {files[i]}: {result}")
            else:
                self.results.add(result)

        self.results.end_time = datetime.now()
        logger.info(
            f"[FileClassifier] Classification completed: {self.results.success_count}/{self.results.total_files} successful"
        )

        return self.results

    def _scan_files(self, source_dir: Path) -> list[Path]:
        """
        Scan files in a directory.

        Args:
            source_dir: Source directory

        Returns:
            List of file paths
        """
        files = []
        config = self.rules.file_handling

        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip hidden files
            if config.skip_hidden_files and file_path.name.startswith("."):
                continue

            # Skip system files
            if config.skip_system_files and file_path.name.startswith(("~", "Thumbs.db", ".DS_Store")):
                continue

            # Check file extension
            if config.supported_extensions:
                if file_path.suffix.lower() not in config.supported_extensions:
                    continue

            # Check file size
            try:
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                if file_size_mb > config.max_file_size_mb:
                    logger.warning(f"[FileClassifier] Skipping large file: {file_path} ({file_size_mb:.1f}MB)")
                    continue
            except OSError:
                continue

            files.append(file_path)

        return files

    async def _classify_file(self, file_path: Path) -> ClassificationResult:
        """
        Classify a single file.

        Args:
            file_path: File path

        Returns:
            Classification result
        """
        logger.info(f"[FileClassifier] Classifying: {file_path.name}")

        result = ClassificationResult(source_path=file_path, matches=[])

        try:
            # 1. Parse file with DocMirror
            parse_result = await self._parse_file(file_path)

            # 2. Extract text content
            text_content = self._extract_text(parse_result)

            # 3. Rule matching
            rule_matches = self._match_rules(text_content, file_path)
            result.matches.extend(rule_matches)

            # 4. Conflict resolution & decision
            if result.matches:
                final_match, is_pending = self._resolve_conflicts(result.matches)
                result.category = final_match.category_id
                result.confidence = final_match.confidence
                result.is_pending = is_pending

                # 5. Move file (if not dry_run)
                if not self.dry_run:
                    target_path = self._move_file(file_path, final_match.target_dir)
                    result.target_path = target_path
                    result.success = True
                else:
                    # dry_run mode, only compute target path
                    target_dir = self.output_dir / final_match.target_dir
                    result.target_path = target_dir / file_path.name
                    result.success = True
            else:
                logger.warning(f"[FileClassifier] No matches for: {file_path.name}")
                result.success = False

        except Exception as e:
            logger.error(f"[FileClassifier] Failed to classify {file_path}: {e}")
            result.error = str(e)
            result.success = False

        return result

    async def _parse_file(self, file_path: Path):
        """
        Parse a file using DocMirror.

        Args:
            file_path: File path

        Returns:
            ParseResult object
        """
        from docmirror.input.entry.factory import perceive_document

        try:
            parse_result = await perceive_document(file_path)
            return parse_result
        except Exception as e:
            logger.warning(f"[FileClassifier] DocMirror parsing failed for {file_path}: {e}")
            # Return None; fall back to basic text extraction
            return None

    def _extract_text(self, parse_result) -> str:
        """
        Extract text content from a parse result.

        Args:
            parse_result: ParseResult object

        Returns:
            Extracted text content
        """
        if parse_result is None:
            return ""

        texts = []

        # Extract page text
        if hasattr(parse_result, "pages"):
            for page in parse_result.pages:
                if hasattr(page, "texts"):
                    for text_block in page.texts:
                        if hasattr(text_block, "content") and text_block.content:
                            texts.append(text_block.content)

        # Extract key-value pairs
        if hasattr(parse_result, "pages"):
            for page in parse_result.pages:
                if hasattr(page, "key_values"):
                    for kv in page.key_values:
                        if hasattr(kv, "key") and kv.key:
                            texts.append(f"{kv.key}: {kv.value}")

        # Extract entities
        if hasattr(parse_result, "entities"):
            entities = parse_result.entities
            if hasattr(entities, "domain_specific") and entities.domain_specific:
                for key, value in entities.domain_specific.items():
                    texts.append(f"{key}: {value}")

        return "\n".join(texts)

    def _match_rules(self, text: str, _file_path: Path) -> list[ClassificationMatch]:
        """
        Match a file against classification rules.

        Args:
            text: File text content
            file_path: File path

        Returns:
            List of matching rules
        """
        if not text:
            return []

        matches = []
        for rule, match_count in self.rules.match_text(text):
            # Confidence from keyword hit ratio and rule priority
            confidence = min(1.0, match_count / len(rule.keywords) * 0.7 + rule.priority / 1000 * 0.3)

            matches.append(
                ClassificationMatch(
                    source="rule",
                    category_id=rule.rule_id,
                    category_name=rule.name,
                    target_dir=rule.target_dir,
                    confidence=confidence,
                    details={"matched_keywords": match_count},
                )
            )

        return matches

    def _resolve_conflicts(self, matches: list[ClassificationMatch]) -> tuple[ClassificationMatch, bool]:
        """
        Resolve classification conflicts.

        Args:
            matches: List of match results

        Returns:
            (final match, whether manual review is needed)
        """
        if not matches:
            raise ValueError("No matches to resolve")

        # Sort by confidence
        matches.sort(key=lambda m: m.confidence, reverse=True)

        # Check for multiple matches
        is_pending = False
        config = self.rules.conflict_resolution

        if len(matches) >= config.multi_match_threshold:
            # Check if highest confidence match clearly outperforms others
            best = matches[0]
            second_best = matches[1] if len(matches) > 1 else None

            if second_best and (best.confidence - second_best.confidence) < 0.1:
                # Confidence too close, needs manual review
                is_pending = config.generate_pending_report
                logger.warning(
                    f"[FileClassifier] Multiple close matches: "
                    f"{best.category_name}({best.confidence:.2f}) vs "
                    f"{second_best.category_name}({second_best.confidence:.2f})"
                )

        # Return highest confidence match
        return matches[0], is_pending

    def _move_file(self, source_path: Path, target_dir: str) -> Path:
        """
        移动文件到目标目录

        Args:
            source_path: 源文件路径
            target_dir: 目标目录(相对于output_dir)

        Returns:
            目标文件路径
        """
        target_path = self.output_dir / target_dir / source_path.name

        # Create target directory
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle filename conflict
        if target_path.exists():
            # Add timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = source_path.stem
            suffix = source_path.suffix
            target_path = self.output_dir / target_dir / f"{stem}_{timestamp}{suffix}"

        # Move file
        shutil.copy2(source_path, target_path)
        logger.info(f"[FileClassifier] Moved: {source_path.name} -> {target_path}")

        return target_path
