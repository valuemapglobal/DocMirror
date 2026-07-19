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
| 结构化事实 | `001_community.json`，包含 Community 6+1 路由后的结构化结果 |
| 字段证据 | source refs、页码、bbox、raw values、转换链路 |
| 复核判断 | quality status、confidence、warnings、`needs_review` |
| RAG / Agent 输入 | Markdown 与带来源上下文的结构化 chunks |
| 审计 / Debug 交接 | 可选 `_mirror.json`、evidence bundle、quality report、manifest、visual debug artifact |

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

解析你自己的文件。默认只输出 Community JSON：

```bash
pip install "docmirror[pdf,ocr,office]"
docmirror statement.pdf --output-dir ./output
```

仅需要 Mirror 时使用 `--mirror`；需要排错、审计及完整支持产物时使用公开
quickstart profile：

```bash
docmirror statement.pdf --mirror
docmirror statement.pdf --profile quickstart
```

扫描件 OCR 默认启用确定性的安全纠错。使用 `--ocr-correction suggest`
可只审计候选而不改写输出；使用 `--ocr-correction off` 可仅保留基础字符规范化。
可以通过 `--ocr-language`、`--ocr-country`、`--ocr-locale` 和可重复的
`--ocr-correction-pack` 选择语言、国家及客户规则包。规则维护不需要执行文档解析：

```bash
docmirror ocr-correction validate
docmirror ocr-correction list-packs
docmirror ocr-correction explain "应收账款周转牢" --locale zh-CN --domain financial_report --role field_label
docmirror ocr-correction evaluate ./tests/fixtures/ocr_correction --fail-on-regression
```

项目或客户私有规则包可通过 `DOCMIRROR_OCR_CORRECTION_PACKS` 指定目录；设置
`opt_in: true` 的规则包必须由请求显式启用。审计记录会保留 OCR 原文、规则包 ID/版本、
语言地区、候选分数和唯一性边际。

默认输出：

```text
output/<run_id>/
  001_community.json
```

Community `6+1` 输出不再只是字段和表格的搬运。六个核心场景
（银行流水、微信支付、支付宝、增值税发票、营业执照、征信报告）以及通用兜底都会稳定提供：

- `business`：可直接阅读的业务摘要、关键指标，以及真正派生的期间、排行与金额勾稽；
- `quality`：结构化质量分、`ready / review / insufficient` 可用性、运行问题与证据覆盖；
- `data.field_details`：标准值引用、置信度、来源与复核状态；仅在原文与标准值不同时保留原文；
- `data.datasets`：通过 JSON Pointer 发现交易、发票和征信数据集，不复制大型明细；
- `data.data_dictionary`：字段/数据集列的类型、标签、格式、脱敏策略、覆盖率和可空性；
- `validation.domain_contract`：对 Community 领域契约的真实通过/部分通过状态；
- `projection_lineage`：从 Community 结果回到 Mirror 事实与证据的紧凑血缘。

标准落盘文件使用精简的 Community 2.2，并可与 2.0/2.1 文件共同通过 Schema 读取。内部基础 DEC 仍为 2.0，只有在消费层完整生成后才原子升级。`data.fields` 是标准值唯一位置；中间字段元数据、通用插件中间投影及 VAT 重复别名/基础记录，会在信息进入引用、数据集和数据字典后从最终文件中移除。单插件输出仅使用 `plugin`，`plugins` 仅用于真实组合。
HTML 等展示层根据 `document`、`business`、`quality`、`datasets` 和 `data_dictionary` 自行组装，不进入核心 JSON 数据契约。

对六类之外或未能稳定分类的文档，`generic` 插件仍会运行，并自适应恢复 KV、字段类型、
标准化值、身份语义、表格、章节，以及表格几何丢失后的重复行结构；不会再输出空壳成功结果。
通用投影会使用表头语义与有效值联合判断日期、金额、账号、电话和编号，保留重复或空表头下的
每个单元格，并把低来源覆盖、全文 KV、表头修复、标准化失败和币种不明确转换为可定位的复核提示。
未在原文中明确出现的币种不会被默认推定为人民币。
对于长篇报告，正文编号可用于恢复章节；低置信度、非连续页或表头漂移的跨页合并会保守回退到
原始物理表，避免错误拼接覆盖真实行，同时保持 Community JSON 结构及处理链路不变。
合同编号、证件号码、户号等标识符会保留前导零；保费、工资、利息、租金、税款、净值等
明确金额字段可在原文给出币种时生成带币种的标准化数值。

纯扫描长篇报告建议保持自动分页并显式启用中文 OCR；通用插件会在 OCR 方向确认后才拆分
旋转双页，避免直立报告产生稀疏逻辑页码。示例：

```bash
docmirror scanned-report.pdf --profile community --mode accurate --ocr force \
  --ocr-language zh --ocr-locale zh-CN --ocr-correction safe --page-split auto
```

扫描报告的 `quality.readiness=review` 表示字段或复杂表格仍需人工复核，不应仅凭质量分自动入库；
表头修复会按比例汇总提示，具体受影响表仍可通过 `data.tables[].header_repaired` 定位。
命令行完成后会直接显示实际插件、文档类型、Community 质量分、readiness、警告数量及前三项
复核提示；JSON 的字段层级和数据流程不因此改变。

使用 `--profile quickstart` 时的诊断输出：

```text
output/<run_id>/
  001_mirror.json
  001_community.json
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
  "mirror": {"schema": "docmirror.mirror_json", "schema_version": "1.0.7"},
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
docmirror document.pdf
docmirror document.pdf --mirror --format markdown,chunks --debug-artifact
docmirror ./documents --recursive --output-dir ./output
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
