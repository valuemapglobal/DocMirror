"""
语义熵Monitor与防循环器 (Semantic Entropy Monitor & Loop Breaker)
===============================================================

DeepSeek-OCR 2 的 Repetition Control (重复控制) 理念。
在遇到复杂Table或结构混乱的Document时，VLM/LLM 容易陷入“复读机”Status。
本ModuleviaCalculate文本 N-gram 的频率和Information entropy，实时打断抽取过程的无限循环。
"""

import math
import logging
from typing import List, Dict, Any
from collections import Counter

logger = logging.getLogger(__name__)

class SemanticRepetitionError(Exception):
    """当Detect到 LLM 陷入无限复读时的自define打断Exception"""
    pass

class EntropyMonitor:
    def __init__(self, n_gram_size: int = 15, max_repeat_count: int = 4):
        """
        :param n_gram_size: Detect重复的字符窗口大小。15个字符基本能代 table一个完整的短句或Table行。
        :param max_repeat_count: allow同一 N-gram 重复出现的最大次数。
        """
        self.n_gram_size = n_gram_size
        self.max_repeat_count = max_repeat_count
        
    def _extract_ngrams(self, text: str) -> List[str]:
        # removeWhitespace字符以便于紧凑对比
        compact_text = "".join(text.split())
        ngrams = []
        if len(compact_text) < self.n_gram_size:
            return ngrams
            
        for i in range(len(compact_text) - self.n_gram_size + 1):
            ngrams.append(compact_text[i : i + self.n_gram_size])
            
        return ngrams
        
    def check_loop_hallucination(self, generated_text: str):
        """
        检查生成的文本Whether陷入了“复读机”死循环。
        如果同一个 15 字符的片段重复出现超过 max_repeat_count 次，
        且文本较长（Information entropy极低），则抛出Exception，强制切断。
        """
        if not generated_text or len(generated_text) < 50:
            return
            
        ngrams = self._extract_ngrams(generated_text)
        if not ngrams:
            return
            
        ngram_counts = Counter(ngrams)
        most_common_gram, count = ngram_counts.most_common(1)[0]
        
        if count >= self.max_repeat_count:
            logger.warning(
                f"[v2] ⚠️ Trigger防循环拦截 (Semantic Loop Breaker) !!\n"
                f"高频复读片段: 『{most_common_gram}』, 出现次数: {count}"
            )
            raise SemanticRepetitionError(f"VLM/LLM Hallucination Loop Detected: Re-generation required")
            
    def calculate_shannon_entropy(self, text: str) -> float:
        """
        附加Tool：Calculate字符级香农熵。熵过低说明文本单调/重复。
        可用作后续更精细的 fallback Threshold。
        """
        if not text:
            return 0.0
        compact = "".join(text.split())
        if not compact:
            return 0.0
            
        freqs = Counter(compact)
        length = len(compact)
        entropy = -sum((count / length) * math.log2(count / length) for count in freqs.values())
        return entropy
