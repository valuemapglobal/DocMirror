"""
Pipeline Registry — 按FormatRegisterMiddlewareComposition
==========================================

Extension方式: 在 FORMAT_PIPELINES 中add新Format即可。
"""

from typing import Dict, List


# Format → { 增强Mode → MiddlewareList }
FORMAT_PIPELINES: Dict[str, Dict[str, List[str]]] = {
    "pdf": {
        "raw": [],
        "standard": [
            "SceneDetector",
            "EntityExtractor",
            "InstitutionDetector",
            "ColumnMapper",
            "Validator",
        ],
        "full": [
            "SceneDetector",
            "EntityExtractor",
            "InstitutionDetector",
            "ColumnMapper",
            "Validator",
            "Repairer",
        ],
    },
    "image": {
        "raw": [],
        "standard": ["LanguageDetector", "GenericEntityExtractor"],
    },
    "excel": {
        "raw": [],
        "standard": ["GenericEntityExtractor"],
    },
    "word": {
        "raw": [],
        "standard": ["LanguageDetector", "GenericEntityExtractor"],
    },
    # 通配 fallback: 未RegisterFormatusing
    "*": {
        "raw": [],
        "standard": ["LanguageDetector"],
    },
}


def get_pipeline_config(file_type: str, enhance_mode: str = "standard") -> List[str]:
    """
    获取指定Format + 增强Mode的MiddlewareList。

    Args:
        file_type:    FileFormat (pdf, image, excel, word, ...)
        enhance_mode: 增强Mode (raw, standard, full)

    Returns:
        MiddlewareNameList (按Execute顺序)
    """
    fmt_config = FORMAT_PIPELINES.get(file_type, FORMAT_PIPELINES.get("*", {}))
    return fmt_config.get(enhance_mode, fmt_config.get("standard", []))
