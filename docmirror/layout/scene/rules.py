# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Classification rules — declarative scene and file-handling rules.

Purpose: Defines ``ClassificationRule``, ``RuleManager``, and conflict
resolution config loaded from rulesets.

Main components: ``RuleManager``, ``ClassificationRules``, ``ClassificationRule``.

Upstream: Rules config files.

Downstream: ``scene.evidence_engine``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ClassificationRule:
    """单个分类规则"""

    rule_id: str
    name: str
    keywords: list[str]
    target_dir: str
    priority: int = 100

    def match(self, text: str) -> bool:
        """
        检查文本是否匹配此规则

        Args:
            text: 要检查的文本内容

        Returns:
            如果文本包含任一关键词则返回True
        """
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)

    def match_count(self, text: str) -> int:
        """
        计算文本匹配的关键词数量

        Args:
            text: 要检查的文本内容

        Returns:
            匹配的关键词数量
        """
        text_lower = text.lower()
        return sum(1 for keyword in self.keywords if keyword.lower() in text_lower)


@dataclass
class ConflictResolutionConfig:
    """冲突解决配置"""

    strategy: str = "priority_first"  # priority_first, multi_match_report
    generate_pending_report: bool = True
    multi_match_threshold: int = 2


@dataclass
class FileHandlingConfig:
    """文件处理配置"""

    skip_hidden_files: bool = True
    skip_system_files: bool = True
    max_file_size_mb: int = 500
    supported_extensions: list[str] = field(default_factory=list)


@dataclass
class ClassificationRules:
    """分类规则集合"""

    rules: dict[str, ClassificationRule] = field(default_factory=dict)
    conflict_resolution: ConflictResolutionConfig = field(default_factory=ConflictResolutionConfig)
    file_handling: FileHandlingConfig = field(default_factory=FileHandlingConfig)

    def get_rule(self, rule_id: str) -> ClassificationRule | None:
        """获取指定规则"""
        return self.rules.get(rule_id)

    def get_all_rules(self) -> list[ClassificationRule]:
        """获取所有规则,按优先级降序排序"""
        return sorted(self.rules.values(), key=lambda r: r.priority, reverse=True)

    def match_text(self, text: str) -> list[tuple[ClassificationRule, int]]:
        """
        匹配文本到规则

        Args:
            text: 要匹配的文本内容

        Returns:
            匹配的规则列表,每个元素为(规则, 匹配关键词数)的元组,
            按优先级和匹配数降序排序
        """
        matches = []
        for rule in self.rules.values():
            count = rule.match_count(text)
            if count > 0:
                matches.append((rule, count))

        # 排序: 先按优先级,再按匹配数
        matches.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
        return matches

    def get_target_dirs(self) -> list[str]:
        """获取所有目标目录路径"""
        return list({rule.target_dir for rule in self.rules.values()})


class RuleManager:
    """规则管理器"""

    def __init__(self, rules_path: Path | Traversable | None = None):
        """
        初始化规则管理器

        Args:
            rules_path: 规则配置文件路径,如果为None则使用默认路径
        """
        self.rules_path = rules_path or self._get_default_rules_path()
        self.rules = ClassificationRules()

        if self.rules_path is not None and self.rules_path.is_file():
            self._load_rules(self.rules_path)
        else:
            logger.warning(f"[RuleManager] Rules file not found: {self.rules_path}")

    def _get_default_rules_path(self) -> Traversable | None:
        """获取 generic 插件声明的默认规则资源。"""
        from docmirror.configs.classification.rules_loader import get_classification_rules_resource

        return get_classification_rules_resource()

    def _load_rules(self, path: Path | Traversable) -> None:
        """
        从YAML文件加载规则

        Args:
            path: YAML文件路径
        """
        try:
            with path.open(encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # 加载分类规则
            if "categories" in config:
                for rule_id, rule_data in config["categories"].items():
                    rule = ClassificationRule(
                        rule_id=rule_id,
                        name=rule_data.get("name", rule_id),
                        keywords=rule_data.get("keywords", []),
                        target_dir=rule_data.get("target_dir", ""),
                        priority=rule_data.get("priority", 100),
                    )
                    self.rules.rules[rule_id] = rule

            # 加载冲突解决配置
            if "conflict_resolution" in config:
                cr_config = config["conflict_resolution"]
                self.rules.conflict_resolution = ConflictResolutionConfig(
                    strategy=cr_config.get("strategy", "priority_first"),
                    generate_pending_report=cr_config.get("generate_pending_report", True),
                    multi_match_threshold=cr_config.get("multi_match_threshold", 2),
                )

            # 加载文件处理配置
            if "file_handling" in config:
                fh_config = config["file_handling"]
                self.rules.file_handling = FileHandlingConfig(
                    skip_hidden_files=fh_config.get("skip_hidden_files", True),
                    skip_system_files=fh_config.get("skip_system_files", True),
                    max_file_size_mb=fh_config.get("max_file_size_mb", 500),
                    supported_extensions=fh_config.get("supported_extensions", []),
                )

            logger.info(f"[RuleManager] Loaded {len(self.rules.rules)} rules from {path}")

        except Exception as e:
            logger.error(f"[RuleManager] Failed to load rules from {path}: {e}")
            raise

    def get_rules(self) -> ClassificationRules:
        """获取分类规则集合"""
        return self.rules

    def add_rule(self, rule: ClassificationRule) -> None:
        """
        添加自定义规则

        Args:
            rule: 分类规则对象
        """
        self.rules.rules[rule.rule_id] = rule
        logger.debug(f"[RuleManager] Added rule: {rule.rule_id}")

    def remove_rule(self, rule_id: str) -> bool:
        """
        移除规则

        Args:
            rule_id: 规则ID

        Returns:
            如果成功移除返回True,否则返回False
        """
        if rule_id in self.rules.rules:
            del self.rules.rules[rule_id]
            logger.debug(f"[RuleManager] Removed rule: {rule_id}")
            return True
        return False
