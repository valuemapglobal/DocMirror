# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Core classification engine used by the ``docmirror classify`` CLI.

Orchestrates directory traversal, optional lightweight parsing, document-type
matching against the 120-type taxonomy, and physical file organization into
type-specific output folders. Integrates DocMirror's plugin registry and
parse pipeline so classification decisions can use both text samples and
structured entity hints from partial parses.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from docmirror.core.scene.rules import RuleManager
from docmirror.plugins import PluginRegistry

logger = logging.getLogger(__name__)


@dataclass
class ClassificationMatch:
    """分类匹配结果"""

    source: str  # "rule" 或 "plugin"
    category_id: str
    category_name: str
    target_dir: str
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """单个文件的分类结果"""

    source_path: Path
    category: str | None = None
    target_path: Path | None = None
    matches: list[ClassificationMatch] = field(default_factory=list)
    confidence: float = 0.0
    success: bool = False
    error: str | None = None
    is_pending: bool = False  # 是否需要人工审核


@dataclass
class ClassificationResults:
    """分类结果集合"""

    results: list[ClassificationResult] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def total_files(self) -> int:
        """总文件数"""
        return len(self.results) + len(self.errors)

    @property
    def success_count(self) -> int:
        """成功分类数"""
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        """失败数"""
        return len(self.errors)

    @property
    def unmatched_count(self) -> int:
        """未匹配数"""
        return sum(1 for r in self.results if not r.success and not r.error)

    @property
    def pending_count(self) -> int:
        """待处理数"""
        return sum(1 for r in self.results if r.is_pending)

    @property
    def avg_confidence(self) -> float:
        """平均置信度"""
        successful = [r.confidence for r in self.results if r.success]
        return sum(successful) / len(successful) if successful else 0.0

    def add(self, result: ClassificationResult) -> None:
        """添加分类结果"""
        self.results.append(result)

    def add_error(self, file_path: Path, error: str) -> None:
        """添加错误记录"""
        self.errors.append((file_path, error))

    def get_results_by_category(self) -> dict[str, list[ClassificationResult]]:
        """按类别分组结果"""
        grouped: dict[str, list[ClassificationResult]] = {}
        for result in self.results:
            if result.category:
                if result.category not in grouped:
                    grouped[result.category] = []
                grouped[result.category].append(result)
        return grouped


class FileClassifier:
    """智能文件分类器"""

    def __init__(self, rules_path: Path | None = None, output_dir: Path | None = None, dry_run: bool = False):
        """
        初始化分类器

        Args:
            rules_path: 规则配置文件路径
            output_dir: 输出目录
            dry_run: 是否仅预览不移动文件
        """
        self.rule_manager = RuleManager(rules_path)
        self.rules = self.rule_manager.get_rules()
        self.output_dir = output_dir or Path.cwd() / "classified_output"
        self.dry_run = dry_run
        self.plugin_registry = PluginRegistry()
        self.results = ClassificationResults()

    async def classify_directory(self, source_dir: Path) -> ClassificationResults:
        """
        遍历目录并分类所有文件

        Args:
            source_dir: 源目录路径

        Returns:
            分类结果集合
        """
        import asyncio

        self.results.start_time = datetime.now()
        logger.info(f"[FileClassifier] Starting classification of: {source_dir}")

        # 扫描文件
        files = self._scan_files(source_dir)
        logger.info(f"[FileClassifier] Found {len(files)} files to classify")

        # 并行处理文件
        tasks = [self._classify_file(file_path) for file_path in files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
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
        扫描目录中的文件

        Args:
            source_dir: 源目录

        Returns:
            文件路径列表
        """
        files = []
        config = self.rules.file_handling

        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue

            # 跳过隐藏文件
            if config.skip_hidden_files and file_path.name.startswith("."):
                continue

            # 跳过系统文件
            if config.skip_system_files and file_path.name.startswith(("~", "Thumbs.db", ".DS_Store")):
                continue

            # 检查扩展名
            if config.supported_extensions:
                if file_path.suffix.lower() not in config.supported_extensions:
                    continue

            # 检查文件大小
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
        分类单个文件

        Args:
            file_path: 文件路径

        Returns:
            分类结果
        """
        logger.info(f"[FileClassifier] Classifying: {file_path.name}")

        result = ClassificationResult(source_path=file_path, matches=[])

        try:
            # 1. 使用DocMirror解析文件
            parse_result = await self._parse_file(file_path)

            # 2. 提取文本内容
            text_content = self._extract_text(parse_result)

            # 3. 规则匹配
            rule_matches = self._match_rules(text_content, file_path)
            result.matches.extend(rule_matches)

            # 4. 插件匹配
            plugin_matches = self._match_plugins(parse_result, text_content)
            result.matches.extend(plugin_matches)

            # 5. 冲突解决与决策
            if result.matches:
                final_match, is_pending = self._resolve_conflicts(result.matches)
                result.category = final_match.category_id
                result.confidence = final_match.confidence
                result.is_pending = is_pending

                # 6. 移动文件(如果不是dry_run)
                if not self.dry_run:
                    target_path = self._move_file(file_path, final_match.target_dir)
                    result.target_path = target_path
                    result.success = True
                else:
                    # dry_run模式,只计算目标路径
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
        使用DocMirror解析文件

        Args:
            file_path: 文件路径

        Returns:
            ParseResult对象
        """
        from docmirror.core.entry.factory import perceive_document

        try:
            parse_result = await perceive_document(file_path)
            return parse_result
        except Exception as e:
            logger.warning(f"[FileClassifier] DocMirror parsing failed for {file_path}: {e}")
            # 返回None,后续将使用基础文本提取
            return None

    def _extract_text(self, parse_result) -> str:
        """
        从解析结果中提取文本内容

        Args:
            parse_result: ParseResult对象

        Returns:
            提取的文本内容
        """
        if parse_result is None:
            return ""

        texts = []

        # 提取页面文本
        if hasattr(parse_result, "pages"):
            for page in parse_result.pages:
                if hasattr(page, "texts"):
                    for text_block in page.texts:
                        if hasattr(text_block, "content") and text_block.content:
                            texts.append(text_block.content)

        # 提取键值对
        if hasattr(parse_result, "pages"):
            for page in parse_result.pages:
                if hasattr(page, "key_values"):
                    for kv in page.key_values:
                        if hasattr(kv, "key") and kv.key:
                            texts.append(f"{kv.key}: {kv.value}")

        # 提取实体
        if hasattr(parse_result, "entities"):
            entities = parse_result.entities
            if hasattr(entities, "domain_specific") and entities.domain_specific:
                for key, value in entities.domain_specific.items():
                    texts.append(f"{key}: {value}")

        return "\n".join(texts)

    def _match_rules(self, text: str, _file_path: Path) -> list[ClassificationMatch]:
        """
        使用规则匹配文件

        Args:
            text: 文件文本内容
            file_path: 文件路径

        Returns:
            匹配的规则列表
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

    def _match_plugins(self, _parse_result, text: str) -> list[ClassificationMatch]:
        """
        使用插件匹配文件

        Args:
            parse_result: ParseResult对象
            text: 文件文本内容

        Returns:
            匹配的插件列表
        """
        if not text:
            return []

        matches = []
        document_context = {"text": text}

        # 遍历所有插件
        for (domain_name, ed), plugin in self.plugin_registry._plugins.items():
            try:
                if hasattr(plugin, "match") and plugin.match(document_context):
                    # 插件匹配成功
                    keywords = getattr(plugin, "scene_keywords", [])
                    match_count = sum(1 for kw in keywords if kw in text)
                    confidence = min(1.0, match_count / len(keywords) * 0.8 + 0.2)

                    # Plugin-defined category directory when available
                    target_dir = ""
                    if hasattr(plugin, "get_classification_category"):
                        target_dir = plugin.get_classification_category()
                    else:
                        # 默认使用插件域名作为目录
                        target_dir = f"plugins/{domain_name}"

                    matches.append(
                        ClassificationMatch(
                            source="plugin",
                            category_id=f"plugin_{domain_name}",
                            category_name=plugin.display_name,
                            target_dir=target_dir,
                            confidence=confidence,
                            details={"plugin": domain_name, "matched_keywords": match_count},
                        )
                    )
            except Exception as e:
                logger.debug(f"[FileClassifier] Plugin {domain_name} matching failed: {e}")

        return matches

    def _resolve_conflicts(self, matches: list[ClassificationMatch]) -> tuple[ClassificationMatch, bool]:
        """
        解决分类冲突

        Args:
            matches: 匹配结果列表

        Returns:
            (最终匹配, 是否需要人工审核)
        """
        if not matches:
            raise ValueError("No matches to resolve")

        # 按置信度排序
        matches.sort(key=lambda m: m.confidence, reverse=True)

        # 检查是否为多匹配
        is_pending = False
        config = self.rules.conflict_resolution

        if len(matches) >= config.multi_match_threshold:
            # 检查最高置信度的匹配是否明显优于其他
            best = matches[0]
            second_best = matches[1] if len(matches) > 1 else None

            if second_best and (best.confidence - second_best.confidence) < 0.1:
                # 置信度接近,需要人工审核
                is_pending = config.generate_pending_report
                logger.warning(
                    f"[FileClassifier] Multiple close matches: "
                    f"{best.category_name}({best.confidence:.2f}) vs "
                    f"{second_best.category_name}({second_best.confidence:.2f})"
                )

        # 返回最高置信度的匹配
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

        # 创建目标目录
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 处理文件名冲突
        if target_path.exists():
            # 添加时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = source_path.stem
            suffix = source_path.suffix
            target_path = self.output_dir / target_dir / f"{stem}_{timestamp}{suffix}"

        # 移动文件
        shutil.copy2(source_path, target_path)
        logger.info(f"[FileClassifier] Moved: {source_path.name} -> {target_path}")

        return target_path
