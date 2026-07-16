# DocMirror

[English](README.md) | [简体中文](README_zh-CN.md)

**面向 RAG、Agent、审计与结构化提取的开源商业凭证可信层。**
**Parse. Prove. Trust.**

DocMirror 将银行流水、发票、合同、证照、税单、回单、付款记录等商业凭证，转化为可追溯、可审计、可计算、可进入系统的结构化信号。

它不只是把文档解析出来，而是告诉你：识别出了什么、证据在哪里、是否值得信任。

## 为什么是 DocMirror

大多数文档工具停在文本、表格或 Markdown。DocMirror 面向的是会进入业务、风控、审计、RAG、Agent 和企业系统的字段，所以关键输出都应该带有证据与质量上下文。

| 需求 | DocMirror 输出 |
|---|---|
| 结构化事实 | `001_mirror.json`，包含文档结构、事实、实体、页面 |
| 字段证据 | source refs、页码、bbox、raw values、转换链路 |
| 复核判断 | quality status、confidence、warnings、`needs_review` |
| RAG / Agent 输入 | Markdown 与带来源上下文的结构化 chunks |
| 审计 / Debug 交接 | evidence bundle、quality report、manifest、visual debug artifact |

DocMirror 不是普通 OCR，也不是通用 RAG loader。它占据的品类更明确：**Commercial Document Trust Layer / 商业凭证可信层**。

## 安装

```bash
pip install docmirror
docmirror doctor
```

按需安装公开能力：

```bash
pip install "docmirror[pdf]"      # 数字 PDF
pip install "docmirror[ocr]"      # 扫描件 OCR
pip install "docmirror[office]"   # DOCX/XLSX/PPTX
pip install "docmirror[server]"   # HTTP API
pip install "docmirror[all]"      # 所有公开 OSS extras
```

Enterprise / Finance 商业扩展单独分发，不是开源包基础安装的前置条件。

## 10 分钟可信解析

从本地仓库运行无需私有样本、无需 OCR 依赖的公开 trust quickstart：

```bash
git clone https://github.com/valuemapglobal/docmirror.git
cd docmirror
python3 examples/trust_quickstart.py
```

你会看到一份 synthetic commercial invoice 的字段证据：

```text
DocMirror trust quickstart
document=synthetic_invoice_001 type=commercial_invoice
trust=confidence:0.96 evidence_coverage:1.00 review_required:true
field=invoice_number value=INV-2026-001 confidence=0.99 page=1 bbox=[88, 112, 236, 132] source_ref=synthetic_invoice_001#page=1&bbox=88,112,236,132 status=ok
```

解析你自己的文件：

```bash
pip install "docmirror[pdf,ocr,office]"
docmirror parse statement.pdf \
  --format json,markdown,chunks \
  --output-dir ./output \
  --debug-artifact
```

典型输出：

```text
output/<run_id>/
  001_mirror.json
  001_community.json
  001.md
  001.chunks.json
  005_evidence_bundle.json
  output.md
  quality_report.json
  visual_debug.html
  manifest.json
```

## Python API

```python
import asyncio
from docmirror import perceive_document

async def main():
    result = await perceive_document("statement.pdf")
    mirror = result.to_mirror_json_vnext()

    print(mirror["mirror"]["schema_version"])
    print(mirror["document"].get("document_type"))
    print(mirror["quality"].get("overall", {}))

    for fact in mirror.get("semantics", {}).get("facts", []):
        evidence = fact.get("evidence") or {}
        print({
            "field": fact.get("field") or fact.get("name"),
            "value": fact.get("value"),
            "page": evidence.get("page"),
            "bbox": evidence.get("bbox"),
            "source_ref": evidence.get("source_ref"),
            "confidence": fact.get("confidence"),
            "needs_review": fact.get("needs_review", False),
        })

asyncio.run(main())
```

## Canonical 输出结构

DocMirror 的 Mirror 输出是 document-shaped，并且保留 evidence / quality 上下文：

```json
{
  "mirror": {"schema": "docmirror.mirror_json", "schema_version": "1.0.1"},
  "source": {"filename": "statement.pdf"},
  "document": {"document_type": "bank_statement", "document_type_candidates": []},
  "pages": [],
  "evidence": {"text_atoms": [], "visual_atoms": []},
  "regions": [],
  "blocks": [],
  "graph": {},
  "semantics": {"facts": [], "entities": [], "views": {}},
  "quality": {"overall": {"status": "pass", "score": 1.0}},
  "diagnostics": {},
  "assets": {}
}
```

关键原则很简单：字段必须尽量带有证据和质量信息，这样下游系统才能决定自动使用、人工复核或拒绝入库。

## 常见工作流

### CLI

```bash
docmirror parse document.pdf --format json
docmirror parse document.pdf --format json,markdown,chunks --debug-artifact
docmirror parse ./documents --recursive --output-dir ./output
docmirror plugins list
```

### API Server

```bash
pip install "docmirror[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

## Community / Enterprise / Finance

| 版本 | 定位 |
|---|---|
| Community | 开源可信层、公开 domains、Mirror JSON、evidence、quality、CLI/API |
| Enterprise | 生产级批处理、运维、私有部署、支持、治理 |
| Finance | 金融文档深度提取、现金流特征、交易对手归并、审计证据 |

Community 版不会故意削弱 Mirror、Evidence、Quality Report 和失败可见性，因为这些是 DocMirror 建立开源标准的核心。

## 已知边界

- OCR 精度依赖扫描质量和可选 OCR 依赖。
- 复杂合并表格和特殊阅读顺序可能需要人工复核。
- 商业扩展能力由单独分发的包提供。

## 社区

- 文档：[valuemapglobal.github.io/docmirror](https://valuemapglobal.github.io/docmirror/)
- 快速开始：[docs/quickstart.md](docs/quickstart.md)
- Issue：[github.com/valuemapglobal/docmirror/issues](https://github.com/valuemapglobal/docmirror/issues)
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全：[SECURITY.md](SECURITY.md)

由 **Adam Lin** 创建，**ValueMap Global** 维护。Apache 2.0 许可。
