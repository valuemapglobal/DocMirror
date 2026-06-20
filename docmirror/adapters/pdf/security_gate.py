# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
PDF security gate — DRM stripping and password unlock helper.

Probes PDF files for encryption, attempts heuristic and user-supplied
password unlock via fitz, and writes decrypted copies to disk for downstream
``CoreExtractor`` parsing. Used internally by the PDF adapter path.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFSecurityGate:
    """
    DocMirror PDF Security Decryption Wrapper
    =========================================
    Provides Disk-to-Disk memory-mapped DRM stripping and AES-256 decryption.
    Implements a zero-overhead probe and heuristic dictionary attacks (ID cards/phones).
    """

    @classmethod
    def unlock_file(cls, path: Path, provided_pwd: str = "") -> Path:
        """
        Unlocks a PDF file on disk. If locked, decrypts and saves via pure C++ streaming.
        Returns the safe Path. Zero Python memory allocation.
        """
        try:
            import pikepdf
        except ImportError:
            logger.warning("[SecurityGate] Pikepdf not installed. Bypassing advanced DRM removal.")
            return path

        # 1. Zero-Overhead Probe (Memory mapped via C++, NO python bytes allocated)
        try:
            if not pikepdf.is_encrypted(str(path)):
                return path
        except Exception as e:
            logger.warning(f"[SecurityGate] Probe failed on file: {e}")
            return path

        logger.warning(f"🔒 [SecurityGate] DRM or Encryption Detected on {path.name}. Initiating Breach Protocol...")

        filename = path.name
        # 2. Build Heuristic Attack Dictionary
        attack_dict: list[str] = []
        if provided_pwd:
            attack_dict.append(provided_pwd)
        attack_dict.append("")  # For standard DRM locks (Owner password only)

        # Heuristic 1: Extract ID Card last 6 digits from filename (PBOC Credit Reports)
        id_match = re.search(r"(\d{17}[\dXx])", filename)
        if id_match:
            last_6 = id_match.group(1)[-6:]
            attack_dict.append(last_6)
            attack_dict.append(last_6.upper())
            attack_dict.append(last_6.lower())
            logger.info(f"[SecurityGate] Synthesized target from ID heuristic: ******{last_6}")

        # Heuristic 2: Extract Mobile Number last 6 digits
        phone_match = re.search(r"(?<!\d)(1\d{10})(?!\d)", filename)
        if phone_match:
            last_6 = phone_match.group(1)[-6:]
            attack_dict.append(last_6)
            logger.info(f"[SecurityGate] Synthesized target from Mobile heuristic: ******{last_6}")

        # Remove duplicates while preserving order
        seen = set()
        attack_dict = [x for x in attack_dict if not (x in seen or seen.add(x))]

        # 3. Direct Disk-to-Disk Memory Mapped Execution (OOM Proof)
        for pwd in attack_dict:
            try:
                # Pikepdf maps the file to memory. 0 bytes consumed in Python!
                with pikepdf.open(str(path), password=pwd) as pdf:
                    import os
                    import tempfile

                    # Proper FD management: generate unique path but don't hold the python lock
                    tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                    tf.close()
                    temp_path = tf.name

                    try:
                        pdf.save(temp_path)
                    except Exception as inner_e:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        raise inner_e

                    safe_path = Path(temp_path)
                    logger.info(f"✅ [SecurityGate] Firewall Breached. Streamed DRM-free payload to {safe_path}")
                    return safe_path
            except pikepdf.PasswordError:
                continue
            except Exception as e:
                logger.error(f"[SecurityGate] Fatal Pikepdf Error during breach: {e}")
                return path

        logger.error("❌ [SecurityGate] Breach Failed. Exhausted heuristic dictionary.")
        # Return original path, downstream PyMuPDF will either crash gracefully or read standard pages
        return path
