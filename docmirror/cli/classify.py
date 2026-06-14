# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
智能文件分类CLI命令
===================

提供命令行接口,实现金融机构文件自动分类。

用法:
    docmirror classify <目录>              # 基本使用
    docmirror classify <目录> -o <输出>    # 指定输出目录
    docmirror classify <目录> --dry-run    # 预览模式
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


@click.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    default=None,
    help='分类输出目录 (默认: ./classified_output)'
)
@click.option(
    '--rules', '-r',
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help='分类规则文件路径 (YAML格式)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    default=False,
    help='仅预览分类结果,不移动文件'
)
@click.option(
    '--report-format',
    type=click.Choice(['markdown', 'json', 'csv']),
    default='markdown',
    help='报告格式 (默认: markdown)'
)
def classify(source_dir, output_dir, rules, dry_run, report_format):
    """
    智能分类目录中的金融文件
    
    遍历SOURCE_DIR中的所有文件,自动解析内容并分类到对应目录。
    基于DocMirror插件系统和规则引擎实现精准分类。
    
    \b
    示例:
      # 基本使用
      docmirror classify /path/to/documents
      
      # 指定输出目录
      docmirror classify /path/to/documents -o /path/to/output
      
      # 预览模式(不移动文件)
      docmirror classify /path/to/documents --dry-run
      
      # 使用自定义规则
      docmirror classify /path/to/documents -r custom_rules.yaml
      
      # 生成JSON报告
      docmirror classify /path/to/documents --report-format json
    """

    # 设置输出目录
    output_dir = output_dir or Path.cwd() / "classified_output"

    console.print("\n" + "=" * 80)
    console.print("[bold cyan]🚀 智能文件分类系统[/bold cyan]")
    console.print("=" * 80)

    console.print(f"\n[bold]源目录:[/bold] {source_dir}")
    console.print(f"[bold]输出目录:[/bold] {output_dir}")
    console.print(f"[bold]规则文件:[/bold] {rules or '默认'}")
    console.print(f"[bold]模式:[/bold] {'预览(不移动文件)' if dry_run else '正式分类'}")
    console.print(f"[bold]报告格式:[/bold] {report_format}\n")

    if dry_run:
        console.print("[yellow]⚠ 预览模式: 文件不会被实际移动[/yellow]\n")

    # 运行分类
    try:
        from docmirror.cli.classify_engine import FileClassifier
        from docmirror.cli.classify_report import (
            generate_pending_report,
            generate_report,
            print_summary,
        )

        classifier = FileClassifier(
            rules_path=rules,
            output_dir=output_dir,
            dry_run=dry_run
        )

        # 执行分类
        results = asyncio.run(classifier.classify_directory(source_dir))

        # 打印摘要
        print_summary(results)

        # 生成报告
        if results.total_files > 0:
            report_path = generate_report(results, output_dir, report_format)
            console.print(f"[bold green]✓[/bold green] 分类报告: {report_path}")

            # 如果有待处理文件,生成待处理报告
            if results.pending_count > 0:
                pending_path = generate_pending_report(results, output_dir)
                console.print(f"[bold yellow]⚠[/bold yellow] 待处理报告: {pending_path}")

        # 返回状态码
        if results.failed_count > 0:
            raise SystemExit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ 分类被用户中断[/yellow]")
        raise SystemExit(130)
    except Exception as e:
        console.print(f"\n[bold red]✖ 分类失败:[/bold red] {e}")
        logger.exception("Classification failed")
        raise SystemExit(1)
