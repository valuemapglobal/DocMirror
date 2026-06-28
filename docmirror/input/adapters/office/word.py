# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Word Adapter — .docx → ParseResult (structured precision)
===========================================================

Extracts paragraphs and tables from Word documents using python-docx.

- **.docx**: Direct extraction via python-docx (canonical input).
- **.doc / .rtf**: Transcoded upstream by ``TranscodingGate`` (FCR binding);
  this adapter only receives ``.docx``.

Processing logic:
    1. Opens the .docx file via ``python-docx.Document``.
    2. Iterates paragraphs → ``TextBlock`` with heading hierarchy.
    3. Iterates tables → ``TableBlock`` with typed ``CellValue``.
    4. OMML math elements → formula TextBlocks.
"""

from __future__ import annotations

import logging

from docmirror.framework.base import BaseParser

logger = logging.getLogger(__name__)


class WordAdapter(BaseParser):
    """Word (.docx) format adapter — python-docx native parsing only."""
