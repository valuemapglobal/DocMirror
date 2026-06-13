# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
智能文件分类模块
================

基于DocMirror插件系统和规则引擎的金融机构文件自动分类功能。

主要组件:
- FileClassifier: 分类引擎核心
- RuleManager: 规则管理
- generate_report: 报告生成

使用示例:
    from docmirror.core.classification import FileClassifier
    
    classifier = FileClassifier(output_dir=Path("./classified"))
    results = await classifier.classify_directory(Path("./documents"))
"""

from docmirror.core.classification.classifier import ClassificationResult, ClassificationResults, FileClassifier
from docmirror.core.classification.report import generate_pending_report, generate_report, print_summary
from docmirror.core.classification.rules import ClassificationRule, ClassificationRules, RuleManager

__all__ = [
    "FileClassifier",
    "ClassificationResult",
    "ClassificationResults",
    "RuleManager",
    "ClassificationRule",
    "ClassificationRules",
    "generate_report",
    "generate_pending_report",
    "print_summary",
]
