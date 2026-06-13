# DocMirror 插件开发规范 v2.0

## 📋 目录

1. [插件架构原则](#插件架构原则)
2. [标准插件结构](#标准插件结构)
3. [高级插件分层架构](#高级插件分层架构)
4. [文件职责定义](#文件职责定义)
5. [命名规范](#命名规范)
6. [代码规范](#代码规范)
7. [示例模板](#示例模板)

---

## 插件架构原则

### 核心原则

**一种文件类型 = 一个插件文件夹 = 一个DomainPlugin**

### 设计目标

1. ✅ **统一接口**：所有插件继承 `DomainPlugin`
2. ✅ **自动发现**：pkgutil 自动扫描注册
3. ✅ **可扩展性**：支持简单/复杂两种场景
4. ✅ **可维护性**：清晰的职责分层
5. ✅ **可测试性**：独立模块，易于单元测试

---

## 标准插件结构

### 简单插件（推荐 80% 场景）

适用于：身份证、营业执照、护照等结构化文档

```
docmirror/plugins/{plugin_name}/
├── __init__.py          # 导出 Plugin 类和 plugin 实例
└── plugin.py            # 插件核心逻辑 + 末尾 plugin = PluginNamePlugin()
```

**特点**：
- 单一文件实现所有逻辑
- 正则表达式提取实体
- 适合结构化/半结构化文档

**示例**：id_card, business_license, passport

---

### 表格型插件（`table_document`）

跨页流水/明细插件 **必须** 通过统一读表层消费 Mirror，不要直接假设 `pages[0].tables` 已合并：

```python
from docmirror.core.table.table_access import get_logical_tables, table_flatten

logical = get_logical_tables(parse_result)  # 优先 logical_tables，fallback legacy
rows = table_flatten(parse_result)
```

详见 `docs/design/05_table_layer_first_principles_redesign.md`。

---

### 高级插件（复杂场景）

适用于：银行流水、审计报告、征信报告等复杂文档

```
docmirror/plugins/{plugin_name}/
├── __init__.py              # 导出 Plugin 类和核心组件
├── plugin.py                # 插件核心逻辑 + 末尾 plugin = PluginNamePlugin()
│
├── extractors/              # 📦 提取器模块（可选）
│   ├── __init__.py
│   ├── entity_extractor.py  # 实体提取
│   ├── table_extractor.py   # 表格提取
│   └── relation_extractor.py # 关系提取
│
├── processors/              # 🔧 处理器模块（可选）
│   ├── __init__.py
│   ├── ocr_postprocessor.py # OCR 后处理
│   ├── data_validator.py    # 数据校验
│   └── normalizer.py        # 数据标准化
│
├── detectors/               # 🔍 检测器模块（可选）
│   ├── __init__.py
│   ├── template_detector.py # 模板检测
│   └── visual_detector.py   # 视觉检测
│
├── models/                  # 📊 数据模型（可选）
│   ├── __init__.py
│   ├── entities.py          # 实体定义
│   └── templates.py         # 模板定义
│
├── configs/                 # ⚙️ 配置模块（可选）
│   ├── __init__.py
│   ├── constants.py         # 常量定义
│   └── patterns.py          # 正则模式
│
├── templates/               # 📄 模板文件（可选）
│   ├── bank_a.json
│   └── bank_b.json
│
└── README.md                # 📖 插件文档
```

**特点**：
- 分层架构，职责清晰
- 支持复杂处理链路
- 适合多步骤、多模块场景

**示例**：bank_statement, audit_report, credit_report

---

## 高级插件分层架构

### 分层设计

```
┌─────────────────────────────────────────────────────────┐
│                    Plugin Layer                         │
│  plugin.py (DomainPlugin - 统一入口)                     │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼──────┐ ┌───▼───────┐ ┌─▼────────────┐
│ Extractors   │ │Processors │ │  Detectors   │
│ (提取层)     │ │ (处理层)  │ │  (检测层)    │
│              │ │           │ │              │
│ - Entity     │ │ - OCR     │ │ - Template   │
│ - Table      │ │ - Valid   │ │ - Visual     │
│ - Relation   │ │ - Normal  │ │ - Format     │
└───────┬──────┘ └───┬───────┘ └─┬────────────┘
        │            │            │
        └────────────┼────────────┘
                     │
              ┌──────▼──────┐
              │   Models    │
              │  (数据层)   │
              │             │
              │ - Entities  │
              │ - Templates │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │   Configs   │
              │  (配置层)   │
              │             │
              │ - Constants │
              │ - Patterns  │
              └─────────────┘
```

### 数据流向

```
输入文档
  │
  ▼
[Plugin.extract()] ────────────────── 统一入口
  │
  ▼
[Detectors] ───────────────────────── 检测文档类型/模板
  │
  ▼
[Extractors] ──────────────────────── 提取实体/表格/关系
  │
  ▼
[Processors] ──────────────────────── OCR修复/校验/标准化
  │
  ▼
[Models] ──────────────────────────── 数据结构化
  │
  ▼
输出 ParseResult
```

---

## 文件职责定义

### 核心文件（必需）

#### `plugin.py`
- **职责**：插件主入口，继承 DomainPlugin
- **必需方法**：
  - `domain_name`: 插件域名
  - `display_name`: 显示名称
  - `scene_keywords`: 场景关键词
  - `match()`: 文档匹配
  - `extract()`: 实体提取
- **示例**：

```python
class PluginNamePlugin(DomainPlugin):
    """插件名称专用插件"""
    
    @property
    def domain_name(self) -> str:
        return "plugin_name"
    
    async def extract(self, document_context, **kwargs):
        # 1. 调用提取器
        entities = await self._extract_entities(document_context)
        
        # 2. 调用处理器
        entities = await self._process_entities(entities)
        
        # 3. 返回结果
        return {"entities": entities, "confidence": 0.9}
```

#### `__init__.py`
- **职责**：导出 Plugin 类和核心组件
- **内容**：

```python
"""Plugin Name Plugin"""

from .plugin import PluginNamePlugin, plugin

# 导出核心组件（高级插件）
from .extractors import EntityExtractor, TableExtractor
from .processors import OCRPostProcessor, DataValidator

__all__ = [
    "PluginNamePlugin", 
    "plugin",
    # 核心组件
    "EntityExtractor",
    "TableExtractor",
    "OCRPostProcessor",
    "DataValidator",
]
```

`plugin.py` 末尾创建单例（`PluginRegistry` 通过 `plugin.py` 自动发现）：

```python
plugin = PluginNamePlugin()
```

### 扩展文件（可选）

#### `extractors/entity_extractor.py`
- **职责**：实体提取逻辑
- **示例**：

```python
class EntityExtractor:
    """实体提取器"""
    
    def extract(self, text: str) -> Dict[str, Any]:
        entities = {}
        # 提取逻辑
        return entities
```

#### `processors/ocr_postprocessor.py`
- **职责**：OCR 错误修复
- **示例**：

```python
class OCRPostProcessor:
    """OCR 后处理器"""
    
    def fix_number_ocr_errors(self, text: str) -> str:
        # 修复数字 OCR 错误
        return fixed_text
```

#### `processors/data_validator.py`
- **职责**：数据校验和修复
- **示例**：

```python
class DataValidator:
    """数据校验器"""
    
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        # 校验逻辑
        return result
```

#### `detectors/template_detector.py`
- **职责**：模板检测和匹配
- **示例**：

```python
class TemplateDetector:
    """模板检测器"""
    
    def detect(self, document_context: Dict) -> str:
        # 检测最佳匹配模板
        return template_id
```

#### `models/entities.py`
- **职责**：实体数据模型定义
- **示例**：

```python
from dataclasses import dataclass

@dataclass
class PluginNameEntities:
    """插件名称实体"""
    field1: Optional[str] = None
    field2: Optional[str] = None
    confidence: float = 0.0
```

#### `configs/constants.py`
- **职责**：配置常量和正则模式
- **示例**：

```python
# 字段正则模式
FIELD_PATTERNS = {
    "field1": r"字段1[：:]([\u4e00-\u9fa5]+)",
    "field2": r"字段2[：:](\d+)",
}

# 校验规则
VALIDATION_RULES = {
    "field2": {"min": 0, "max": 100},
}
```

---

## 命名规范

### 文件命名

- ✅ **小写 + 下划线**：`entity_extractor.py`
- ✅ **复数形式**：`extractors/`, `processors/`
- ❌ **驼峰命名**：`EntityExtractor.py`
- ❌ **中文命名**：`提取器.py`

### 类命名

- ✅ **大驼峰 + 领域前缀**：`BankStatementTemplate`
- ✅ **后缀明确**：`Extractor`, `Processor`, `Detector`
- ❌ **无后缀**：`BankStatement`
- ❌ **通用名称**：`Helper`, `Utils`

### 方法命名

- ✅ **小写 + 下划线**：`extract_entities()`
- ✅ **动词开头**：`extract_`, `process_`, `validate_`, `detect_`
- ❌ **名词开头**：`entity_extraction()`

### 变量命名

- ✅ **小写 + 下划线**：`entity_count`
- ✅ **语义明确**：`transaction_list`
- ❌ **单字母**：`x`, `tmp`
- ❌ **拼音**：`jine` (应为 `amount`)

---

## 代码规范

### 1. 日志规范

```python
import logging

logger = logging.getLogger(__name__)

# ✅ 正确
logger.info(f"[PluginName] ▶ extract | file={file_path}")
logger.debug(f"[PluginName] Extracted {count} entities")
logger.warning(f"[PluginName] Field '{field}' may be incomplete")
logger.error(f"[PluginName] Extraction failed: {error}")

# ❌ 错误
print("提取完成")
logging.debug("done")
```

### 2. 错误处理

```python
# ✅ 正确
try:
    entities = await self._extract_entities(document_context)
except ValueError as e:
    logger.error(f"[PluginName] Invalid data: {e}")
    return {"entities": {}, "confidence": 0.0, "error": str(e)}
except Exception as e:
    logger.error(f"[PluginName] Unexpected error: {e}")
    raise

# ❌ 错误
entities = extract(document)  # 无错误处理
```

### 3. 类型注解

```python
# ✅ 正确
async def extract(
    self,
    document_context: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    pass

# ❌ 错误
async def extract(self, document_context, **kwargs):
    pass
```

### 4. 文档字符串

```python
# ✅ 正确
class EntityExtractor:
    """实体提取器
    
    从文档文本中提取结构化实体。
    
    支持的实体类型：
    - 个人信息（姓名、身份证号等）
    - 报告信息（报告编号、日期等）
    
    Usage:
        extractor = EntityExtractor()
        entities = extractor.extract(text)
    """
    
    def extract(self, text: str) -> Dict[str, Any]:
        """提取实体
        
        Args:
            text: 文档文本
            
        Returns:
            实体字典
        """
        pass

# ❌ 错误
class EntityExtractor:
    """提取器"""
    def extract(self, text):
        pass
```

### 5. 正则表达式

```python
# ✅ 正确 - 使用原始字符串和命名组
PATTERN = r"(?P<name>[\u4e00-\u9fa5]{2,10})"
match = re.search(PATTERN, text)
if match:
    name = match.group("name")

# ❌ 错误 - 普通字符串
PATTERN = "(?P<name>[\u4e00-\u9fa5]{2,10})"
```

---

## 示例模板

### 简单插件示例

参见：`docmirror/plugins/id_card/`

### 高级插件示例

参见：`docmirror/plugins/bank_statement/`（重构后）

---

## 迁移指南

### 旧插件迁移步骤

1. **创建标准结构**
   ```bash
   mkdir -p plugin_name/{extractors,processors,detectors,models,configs}
   ```

2. **移动文件到对应目录**
   ```
   entity_extractor.py    → extractors/entity_extractor.py
   ocr_postprocessor.py   → processors/ocr_postprocessor.py
   data_validator.py      → processors/data_validator.py
   ```

3. **更新导入路径**
   ```python
   # 旧
   from .ocr_postprocessor import OCRPostProcessor
   
   # 新
   from .processors.ocr_postprocessor import OCRPostProcessor
   ```

4. **创建 plugin.py**
   - 继承 DomainPlugin
   - 实现 extract() 方法
   - 调用提取器和处理器
   - 文件末尾添加 `plugin = PluginNamePlugin()`

5. **更新 __init__.py**
   - 导出 Plugin 类和核心组件

6. **测试验证**
   ```python
   from docmirror.plugins import registry
   plugins = registry.list_plugins()
   assert "plugin_name" in plugins
   ```

---

## 最佳实践

### ✅ 推荐做法

1. **简单场景优先使用简单插件**
   - 80% 的场景只需 plugin.py

2. **复杂场景再分层**
   - 当 plugin.py 超过 300 行时考虑分层

3. **保持模块独立性**
   - 每个模块可独立测试

4. **使用 dataclass 定义实体**
   - 类型安全，代码清晰

5. **编写单元测试**
   - 每个提取器/处理器都有对应测试

### ❌ 避免做法

1. **不要在 plugin.py 中写所有逻辑**
   - 超过 300 行必须分层

2. **不要混用 Middleware 和 DomainPlugin**
   - 统一使用 DomainPlugin

3. **不要硬编码配置**
   - 使用 configs/ 目录

4. **不要忽略错误处理**
   - 所有异常都要捕获和记录

5. **不要跳过类型注解**
   - 提高代码可读性和可维护性

---

## 版本历史

- **v2.0** (2026-04-08): 增加高级插件分层架构
- **v1.0** (2026-04-01): 初始版本，定义标准插件结构

---

## 参考资料

- [创建插件指南](../../docs/plugins/creating-plugins.md)
- [插件架构概览](../../docs/plugins/overview.md)
- [DomainPlugin 接口定义](../../docmirror/plugins/__init__.py)
