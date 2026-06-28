# DocMirror

**商业凭证的可信文档智能层。**  
**Parse. Prove. Trust.**

Category: **Commercial Document Trust Layer**.

DocMirror 将银行流水、发票、合同、证照、税单、付款记录等商业凭证，转化为可追溯、可审计、可计算、可进入系统的结构化信号。

DocMirror 不是普通 OCR，也不是通用 RAG loader。它的核心承诺是：

> 每一个关键字段都应该能说明：来自哪里、在哪一页、哪个区域、置信度多少、是否需要复核。

## 核心能力

- **Parse**：解析真实世界的商业凭证。
- **Prove**：为字段提供 source ref、page、bbox、raw value、转换链路。
- **Trust**：输出质量状态、置信度、异常信号、partial result 和 `needs_review`。

## 安装

```bash
pip install docmirror
```

按需安装能力：

```bash
pip install "docmirror[pdf]"      # 数字 PDF
pip install "docmirror[ocr]"      # 扫描件 OCR
pip install "docmirror[office]"   # DOCX/XLSX/PPTX
pip install "docmirror[server]"   # HTTP API
pip install "docmirror[all]"      # 所有公开 OSS extras
```

## 快速开始

```bash
docmirror --version
docmirror doctor
docmirror parse statement.pdf --format json --output-dir ./output
python examples/trust_quickstart.py
```

```python
import asyncio
from docmirror import perceive_document

async def main():
    result = await perceive_document("statement.pdf")
    mirror = result.to_mirror_json_vnext()

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

## 输出结构

DocMirror 的 canonical mirror 输出包含：

```text
Mirror        事实层
JSON          结构层
Evidence      证据层
Trust Report  可信度/质量层
```

关键原则：

```text
不是只把字段读出来，而是让字段可证明、可复核、可进入下游系统。
```

## 公开能力

| 能力 | 安装方式 |
|---|---|
| 核心 API 和 CLI | `pip install docmirror` |
| 数字 PDF | `pip install "docmirror[pdf]"` |
| 扫描件 OCR | `pip install "docmirror[ocr]"` |
| Office 文件 | `pip install "docmirror[office]"` |
| Server API | `pip install "docmirror[server]"` |
| 公开全量能力 | `pip install "docmirror[all]"` |

企业版和金融版扩展单独分发，不是开源包基础安装的前置条件。

## 命令行

```bash
docmirror parse document.pdf --format json
docmirror parse ./documents --recursive --output-dir ./output
docmirror doctor
docmirror plugins list
```

## 已知边界

- OCR 精度依赖扫描质量和可选 OCR 依赖。
- 复杂合并表格和特殊阅读顺序可能需要人工复核。
- 商业扩展能力由单独分发的包提供。
- 公开 benchmark 数字会以可复现 release gate 为准。
- 可复现的公开 mini benchmark：`python scripts/run_first_benchmark.py --public-mini`。

## 社区

- 文档：[valuemapglobal.github.io/docmirror](https://valuemapglobal.github.io/docmirror/)
- Issue：[github.com/valuemapglobal/docmirror/issues](https://github.com/valuemapglobal/docmirror/issues)
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全：[SECURITY.md](SECURITY.md)

由 **Adam Lin** 创建，**ValueMap Global** 维护。Apache 2.0 许可。
