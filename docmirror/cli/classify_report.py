# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Classification report generator for the DocMirror CLI.

Builds aggregate statistics from a completed ``docmirror classify`` run and
writes human-readable or machine-readable summaries. Supports Markdown tables
for terminal review, JSON for downstream automation, and CSV for spreadsheet
import. Report sections typically include per-type counts, confidence
distribution, unmatched files, and institution breakdowns when available.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from docmirror.cli.classify_engine import ClassificationResults

logger = logging.getLogger(__name__)


def generate_report(results: ClassificationResults, output_dir: Path, format: str = "markdown") -> Path:
    """
    生成分类报告

    Args:
        results: 分类结果
        output_dir: 输出目录
        format: 报告格式(markdown, json, csv)

    Returns:
        报告文件路径
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == "markdown":
        report_path = output_dir / "classification_report.md"
        _generate_markdown_report(results, report_path)
    elif format == "json":
        report_path = output_dir / "classification_report.json"
        _generate_json_report(results, report_path)
    elif format == "csv":
        report_path = output_dir / "classification_report.csv"
        _generate_csv_report(results, report_path)
    else:
        raise ValueError(f"Unsupported report format: {format}")

    logger.info(f"[Report] Generated {format} report: {report_path}")
    return report_path


def generate_pending_report(results: ClassificationResults, output_dir: Path) -> Path:
    """
    生成待处理文件报告

    Args:
        results: 分类结果
        output_dir: 输出目录

    Returns:
        待处理报告文件路径
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pending_review.json"

    pending_results = [r for r in results.results if r.is_pending]

    report_data = {
        "total_pending": len(pending_results),
        "files": [
            {
                "source_path": str(r.source_path),
                "target_path": str(r.target_path) if r.target_path else None,
                "category": r.category,
                "confidence": r.confidence,
                "matches": [
                    {
                        "source": m.source,
                        "category_id": m.category_id,
                        "category_name": m.category_name,
                        "confidence": m.confidence,
                        "details": m.details,
                    }
                    for m in r.matches
                ],
            }
            for r in pending_results
        ],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    logger.info(f"[Report] Generated pending review report: {report_path}")
    return report_path


def _generate_markdown_report(results: ClassificationResults, report_path: Path) -> None:
    """生成Markdown格式报告"""

    # 计算统计数据
    category_stats = results.get_results_by_category()

    # 生成报告内容
    report = f"""# 智能文件分类报告

## 分类概览

- **总文件数**: {results.total_files}
- **成功分类**: {results.success_count}
- **分类失败**: {results.failed_count}
- **未匹配文件**: {results.unmatched_count}
- **待处理文件**: {results.pending_count}
- **平均置信度**: {results.avg_confidence:.2%}
- **处理时间**: {_format_duration(results.start_time, results.end_time)}

## 按类别统计

| 类别 | 文件数 | 占比 |
|------|--------|------|
"""

    for category, cat_results in sorted(category_stats.items()):
        count = len(cat_results)
        percentage = count / results.total_files * 100 if results.total_files > 0 else 0
        report += f"| {category} | {count} | {percentage:.1f}% |\n"

    report += """
## 成功分类文件

| 序号 | 文件名 | 分类 | 目标路径 | 置信度 |
|------|--------|------|----------|--------|
"""

    for i, result in enumerate([r for r in results.results if r.success], 1):
        report += f"| {i} | {result.source_path.name} | {result.category or 'N/A'} | {result.target_path or 'N/A'} | {result.confidence:.2%} |\n"

    # 待处理文件
    pending_results = [r for r in results.results if r.is_pending]
    if pending_results:
        report += """
## 待处理文件(需要人工审核)

| 序号 | 文件名 | 推荐分类 | 置信度 | 匹配数 |
|------|--------|----------|--------|--------|
"""

        for i, result in enumerate(pending_results, 1):
            report += f"| {i} | {result.source_path.name} | {result.category or 'N/A'} | {result.confidence:.2%} | {len(result.matches)} |\n"

    # 错误文件
    if results.errors:
        report += """
## 异常文件

| 序号 | 文件名 | 错误信息 |
|------|--------|----------|
"""

        for i, (file_path, error) in enumerate(results.errors, 1):
            report += f"| {i} | {file_path.name} | {error} |\n"

    # 未匹配文件
    unmatched_results = [r for r in results.results if not r.success and not r.error]
    if unmatched_results:
        report += """
## 未匹配文件

| 序号 | 文件名 | 路径 |
|------|--------|------|
"""

        for i, result in enumerate(unmatched_results, 1):
            report += f"| {i} | {result.source_path.name} | {result.source_path} |\n"

    # 写入文件
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)


def _generate_json_report(results: ClassificationResults, report_path: Path) -> None:
    """生成JSON格式报告"""

    report_data = {
        "summary": {
            "total_files": results.total_files,
            "success_count": results.success_count,
            "failed_count": results.failed_count,
            "unmatched_count": results.unmatched_count,
            "pending_count": results.pending_count,
            "avg_confidence": results.avg_confidence,
            "start_time": results.start_time.isoformat() if results.start_time else None,
            "end_time": results.end_time.isoformat() if results.end_time else None,
        },
        "category_stats": {},
        "files": [],
        "errors": [],
        "unmatched": [],
    }

    # 类别统计
    category_stats = results.get_results_by_category()
    for category, cat_results in category_stats.items():
        report_data["category_stats"][category] = {
            "count": len(cat_results),
            "files": [str(r.source_path.name) for r in cat_results],
        }

    # 文件详情
    for result in results.results:
        if result.success:
            report_data["files"].append(
                {
                    "source_path": str(result.source_path),
                    "target_path": str(result.target_path) if result.target_path else None,
                    "category": result.category,
                    "confidence": result.confidence,
                    "matches": [
                        {
                            "source": m.source,
                            "category_id": m.category_id,
                            "category_name": m.category_name,
                            "confidence": m.confidence,
                        }
                        for m in result.matches
                    ],
                }
            )
        elif not result.error:
            report_data["unmatched"].append(str(result.source_path))

    # 错误信息
    for file_path, error in results.errors:
        report_data["errors"].append({"file_path": str(file_path), "error": error})

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)


def _generate_csv_report(results: ClassificationResults, report_path: Path) -> None:
    """生成CSV格式报告"""

    with open(report_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        # 写入表头
        writer.writerow(["序号", "文件名", "源路径", "目标路径", "分类", "置信度", "状态", "错误信息", "匹配数"])

        # 写入数据
        for i, result in enumerate(results.results, 1):
            status = "成功" if result.success else ("失败" if result.error else "未匹配")
            writer.writerow(
                [
                    i,
                    result.source_path.name,
                    str(result.source_path),
                    str(result.target_path) if result.target_path else "",
                    result.category or "",
                    f"{result.confidence:.2%}",
                    status,
                    result.error or "",
                    len(result.matches),
                ]
            )

        # 写入错误记录
        for i, (file_path, error) in enumerate(results.errors, len(results.results) + 1):
            writer.writerow([i, file_path.name, str(file_path), "", "", "", "错误", error, 0])


def _format_duration(start_time, end_time) -> str:
    """格式化时间间隔"""
    if not start_time or not end_time:
        return "N/A"

    duration = end_time - start_time
    total_seconds = int(duration.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds}秒"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}分{seconds}秒"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}小时{minutes}分"


def print_summary(results: ClassificationResults) -> None:
    """
    打印分类摘要到控制台

    Args:
        results: 分类结果
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n" + "=" * 80)
    console.print("[bold cyan]智能文件分类完成[/bold cyan]")
    console.print("=" * 80)

    # 概览统计
    console.print(f"\n[bold]总文件数:[/bold] {results.total_files}")
    console.print(f"[bold green]成功分类:[/bold green] {results.success_count}")
    console.print(f"[bold red]分类失败:[/bold red] {results.failed_count}")
    console.print(f"[bold yellow]未匹配文件:[/bold yellow] {results.unmatched_count}")
    console.print(f"[bold magenta]待处理文件:[/bold magenta] {results.pending_count}")
    console.print(f"[bold]平均置信度:[/bold] {results.avg_confidence:.2%}")
    console.print(f"[bold]处理时间:[/bold] {_format_duration(results.start_time, results.end_time)}")

    # 类别统计
    category_stats = results.get_results_by_category()
    if category_stats:
        console.print("\n[bold]按类别统计:[/bold]")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("类别", style="cyan")
        table.add_column("文件数", justify="right")
        table.add_column("占比", justify="right")

        for category, cat_results in sorted(category_stats.items()):
            count = len(cat_results)
            percentage = count / results.total_files * 100 if results.total_files > 0 else 0
            table.add_row(category, str(count), f"{percentage:.1f}%")

        console.print(table)

    # 待处理文件提示
    if results.pending_count > 0:
        console.print(f"\n[yellow]⚠ 有 {results.pending_count} 个文件需要人工审核,请查看 pending_review.json[/yellow]")

    # 错误提示
    if results.failed_count > 0:
        console.print(f"\n[red]✖ 有 {results.failed_count} 个文件分类失败,请查看报告详情[/red]")

    console.print()
