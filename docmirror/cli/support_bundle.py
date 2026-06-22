"""``docmirror support bundle`` — GA 1.0 Step 11.

Generates a redacted support bundle for enterprise customer support.

Usage::

    docmirror support bundle <task_id>        # from existing task dir
    docmirror support bundle <file_path>      # auto-parse then bundle
    docmirror support bundle <task_id> --profile forensic_internal
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from tempfile import mkdtemp

import click

logger = logging.getLogger(__name__)


def support_bundle_cmd(
    target: str,
    profile: str = "redacted",
    output: str | None = None,
) -> None:
    """Generate a support bundle from a task directory or file path.

    If *target* is a directory, treat it as an existing task output
    directory and invoke the support bundle packer directly.  If it is
    a file path (or glob), run a parse first and then bundle the result.
    """
    target_path = Path(target)
    output_path = Path(output) if output else None

    # Case 1: target is an existing task directory
    if target_path.is_dir():
        manifest = target_path / "manifest.json"
        if manifest.is_file():
            _bundle_from_task_dir(target_path, profile, output_path)
            return

    # Case 2: target is a file — auto-parse first
    if target_path.is_file():
        from docmirror.cli.explainability_commands import handle_debug_support_bundle
        from docmirror.cli.main import parse as _parse_cmd

        temp_out = Path(mkdtemp(prefix="docmirror_support_"))
        ctx = click.get_current_context()

        # Run parse in ga_full profile to get quality_decision + evidence
        click.echo(f"Parsing {target_path} ...")
        ctx.invoke(
            _parse_cmd,
            file=str(target_path),
            output_dir=str(temp_out),
            profile="ga_full",
            no_save=False,
        )

        # Find the task directory (parse creates a timestamped subdir)
        task_dirs = sorted(temp_out.glob("*/manifest.json"))
        if not task_dirs:
            click.echo("ERROR: Parse completed but no task directory found", err=True)
            sys.exit(1)

        task_dir = task_dirs[0].parent
        bundle_path = handle_debug_support_bundle(task_dir, profile=profile, output=output_path)
        click.echo(f"Support bundle written: {bundle_path}")
        return

    click.echo(f"ERROR: {target} is neither a task directory nor a file", err=True)
    sys.exit(1)


def _bundle_from_task_dir(
    task_dir: Path,
    profile: str,
    output: Path | None,
) -> None:
    """Generate a support bundle from an existing task directory."""
    from docmirror.cli.explainability_commands import handle_debug_support_bundle

    bundle_path = handle_debug_support_bundle(task_dir, profile=profile, output=output)
    click.echo(f"Support bundle written: {bundle_path}")
