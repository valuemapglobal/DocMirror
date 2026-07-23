# DocMirror 研发说明手册

当前发行候选：DocMirror `1.0.11`（兼容性基线：`1.0.0`）
适用对象：后续接手 DocMirror 核心研发、插件研发、服务端/API、SDK、测试与发布维护的同事。
编写日期：2026-06-30

## 1. 项目定位

DocMirror 是面向商业凭证的可信解析层，产品定位是 **Commercial Document Trust Layer**。项目目标不是只把文档转成文本、表格或 Markdown，而是输出可追溯、可审计、可进入业务系统的结构化信号。

核心承诺：

- Parse：从 PDF、图片、Office、邮件、网页、结构化文件、压缩包等输入中解析文档内容。
- Prove：为关键字段、结构、事实和表格保留来源、页码、bbox、置信度、诊断和质量信息。
- Trust：通过质量报告、证据包、可视化调试和 `needs_review` 等信号，帮助下游决定自动入库、人工复核或拒绝。

1.0.x 的主要稳定基线包括：

- Python 包当前版本为 `1.0.11`，公共包名为 `docmirror`。
- Python 支持 `>=3.10`，测试矩阵覆盖 Python 3.10 到 3.13。
- 公共 OSS wheel 只打包 `docmirror` 主包；`docmirror_enterprise`、`docmirror_finance`、`tests`、`scripts`、`docs`、`sdks` 等不进入公共 wheel。
- Canonical 输出是 Mirror JSON vNext，schema 标识为 `docmirror.mirror_json`，当前 schema version 为 `1.0.7`。
- CLI、REST API、Python API 和 edition 输出最终都围绕同一个 `ParseResult`/Mirror 投影链路工作。

## 2. 快速上手

### 2.1 本地开发环境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all,dev,docs]"
pre-commit install
```

最小验证：

```bash
docmirror --help
docmirror doctor
pytest tests/smoke/ -q
```

如果只做轻量核心开发，可先装：

```bash
pip install -e ".[dev]"
```

涉及 PDF、OCR、Office、服务端或 AI/VLM 路径时，再按需安装 extras：

```bash
pip install -e ".[pdf,ocr,office,server,ai,dev]"
```

### 2.2 本地运行

运行公开 quickstart：

```bash
python3 examples/trust_quickstart.py
```

解析单个文件：

```bash
docmirror statement.pdf --output-dir ./output
```

启动 API 服务：

```bash
pip install -e ".[server]"
uvicorn docmirror.server.api:app --host 0.0.0.0 --port 8000
```

Docker 服务：

```bash
docker build -t docmirror:latest .
docker run --rm -p 8000:8000 docmirror:latest
```

## 3. 术语速查

| 缩写/术语 | 含义 | 代码位置 |
|---|---|---|
| FCR | Format Capability Registry，格式能力注册表，负责扩展名/MIME 到 adapter 的路由 | `docmirror/configs/yaml/format_capabilities.yaml` |
| MEP | Middleware Execution Platform，Mirror 层中间件增强管线 | `docmirror/configs/yaml/middleware_catalog.yaml`、`enhancement_profiles.yaml` |
| MOC | Mirror Object Contract，所有 adapter 产出的核心 `ParseResult` 合同 | `docmirror/models/entities/parse_result.py` |
| UDTR | vNext Mirror 主线，文档拓扑、页面、证据、阅读流和语义投影 | `docmirror/models/mirror/`、`docmirror/topology/` |
| PEC | Plugin Execution Contract，封存后的 ParseResult 到 edition 的插件执行合同 | `docmirror/plugins/_runtime/runner.py` |
| DEC | Domain Extraction Contract，领域插件输出的规范化合同 | `docmirror/models/entities/domain_result.py`、`docmirror/models/schemas/` |
| DMIR | 按需序列化的 DocMirror Intermediate Representation，供 MCP/PDF-UA 等专用场景使用 | `docmirror/output/dmir.py` |
| TQG | Test Quality Gate，manifest 驱动的质量门平台 | `docmirror/eval/tqg/`、`tests/regression/` |
| four-file output | CLI/API 持久化的多版本 JSON 输出合同 | `docmirror/server/edition_outputs.py` |

## 4. 仓库结构

```text
docmirror/
  input/             输入接纳、ParsePolicy、adapter、Canonical Assembly
  framework/         Dispatcher、Orchestrator、DI、中间件框架
  layout/            布局分析、页面分区、场景证据、机构线索
  topology/          页面拓扑、阅读顺序、区域图、跨页关系
  ocr/               OCR、扫描件恢复、微网格、局部结构修复
  tables/            表格检测、重建、标准化、流水类表格逻辑
  models/            ParseResult、Mirror vNext、实体、schema、edition serializer
  plugins/           社区领域插件和插件运行时
  output/            Mirror、Community、专用 DMIR/PDF-UA 等只读输出
  evidence/          证据包、source span、visual overlay、diff
  quality/           质量门、质量聚合、review 信号
  configs/           YAML/JSON schema、运行时设置、格式/中间件/领域配置
  runtime/           进度、artifact、checkpoint、scheduler、序列化
  security/          隐私、脱敏、安全检查、egress/resource gate
  server/            FastAPI、MCP、API output builder、artifact pack
  cli/               Click CLI 子命令
  sdk/               Python 客户端集成 helpers
```

周边目录：

```text
docmirror_enterprise/   企业版插件源码，公共 wheel 不打包
docmirror_finance/      金融版插件源码，公共 wheel 不打包
tests/                  单元、契约、回归、集成、e2e 测试
scripts/                质量门、release gate、schema/openapi 生成、架构校验
sdks/                   TypeScript、Go、Java、MCP Server SDK
docs/                   MkDocs 公开文档
examples/               quickstart 和演示脚本
```

## 5. 核心架构

### 5.1 主调用链

```mermaid
flowchart TD
    subgraph entryLayer["① 入口"]
        entry["CLI / REST API / Python SDK"]
        parsePolicy["ParsePolicy<br/>仅包含会改变事实的选项"]
        entry --> parsePolicy
    end

    subgraph parseFlow["② 唯一事实主链"]
        acceptance["InputAcceptance 一次性校验与 FCR"] --> acceptedSource["AcceptedSource 不可变"]
        acceptedSource --> dispatcher["Dispatcher"]
        dispatcher --> adapter["Adapter 证据与基础事实"]
        adapter --> canonical["Canonical Pipeline<br/>唯一事实修改区"]
        canonical --> parseResult["Sealed ParseResult SSOT"]
    end

    entry --> acceptance
    parsePolicy --> dispatcher

    subgraph delivery["③ 只读交付"]
        mirrorProjector["Mirror Projector"]
        communityProjector["Community Projector"]
        enterpriseProjector["Enterprise Projector<br/>内部插件发现与授权"]
        financeProjector["Finance Projector<br/>内部插件发现与授权"]
        projectedArtifacts["内存投影产物"]
        writer["ArtifactWriter<br/>临时文件 + 原子替换"]
        api["REST Response"]
        outputs["固定交付文件 + Manifest"]
        mirrorProjector --> projectedArtifacts
        communityProjector --> projectedArtifacts
        enterpriseProjector --> projectedArtifacts
        financeProjector --> projectedArtifacts
        projectedArtifacts --> api
        projectedArtifacts --> writer --> outputs
    end

    parseResult --> mirrorProjector
    parseResult --> communityProjector
    parseResult --> enterpriseProjector
    parseResult --> financeProjector
```

### 5.2 三个边界要守住

1. Adapter 只产生证据和基础事实；不得执行 Edition 投影，也不得根据输出选择改变解析。
2. Canonical Pipeline 是唯一允许修改事实的区域；领域识别、恢复和校验都必须在 `ParseResult` 封存前完成。
3. Projector 与 Writer 永远只读 `ParseResult`；许可证和包可用性只能决定商业产物是否可交付，不得反向修改事实。

附加硬约束：

- Dispatcher 只接收不可变 `AcceptedSource`，不重复校验、MIME/FCR 解析或 checksum。
- 生产 PDF 主路径由物理证据直接进入 Canonical Assembly，仓库中不存在第二套中间结果模型。
- Mirror 只是独立投影，不是任何插件的隐性输入或运行时缓存。
- 不存在 `ParseResult Cache`、缓存模式或缓存指纹分支；相同输入与 `ParsePolicy` 始终经过同一条事实主链。
- 不存在 Requested Outputs、OutputControl、OutputPlan 或中央 Edition 可用性决策；Mirror 与 Community 固定生成，商业 Projector 在自己的调用边界检查包和授权，失败即不产生投影。
- Projector 负责内存投影，`ArtifactWriter` 只负责原子落盘；两者均不接收普通交付选择参数。
- worker 数和进度回调是调用时运行参数，不建模为核心控制对象；OCR、分页和恢复等会改变结果的选项必须进入 `ParsePolicy`。
- 不存在 Bridge、BaseResult、Projection DAG 或 Visualizer；所有投影从同一个封存后的 `ParseResult` 直接扇出。
- DMIR 不属于普通交付投影，只在 MCP、PDF-UA 等明确调用的专用接口中按需从 `ParseResult` 序列化。

Canonical Pipeline 内部必须保持以下语义顺序，但这些步骤不再膨胀主架构图：

```text
Canonical Assembly → Normalize → Geometric Reconstruction
→ 可选 LLM Restoration → Structure → Entity Extraction
→ Evidence Classification → Institution/Scene Context
→ Domain Facts → Validation/Mutation Audit → Seal
```

这三个边界对应的关键文件：

- `docmirror/framework/base.py`
- `docmirror/framework/dispatcher.py`
- `docmirror/framework/orchestrator.py`
- `docmirror/input/pipeline/__init__.py`
- `docmirror/input/canonical/assembler.py`
- `docmirror/server/output_builder.py`
- `docmirror/server/artifact_writer.py`
- `docmirror/plugins/_runtime/runner.py`

## 6. 输入与解析管线

### 6.1 公共入口

面向集成方的 Python SDK：

```python
from docmirror.sdk import DocMirrorClient

client = DocMirrorClient(output_dir="output")
task = client.parse("statement.pdf")
batch = client.parse_many(["statement.pdf", "license.png"])
```

核心开发者仍可直接调用 `perceive_document()` 获取 `ParseResult`，但该对象和
Mirror JSON 属于解析内部/诊断契约，不作为 REST 或 SDK 的公开返回正文。

CLI：

```bash
docmirror document.pdf
```

文件 CLI 默认持久化 Community 三件套；`--all` 额外持久化 `001_mirror.json` 和
`manifest.json`。当商业扩展已安装且授权有效时，完整模式可以追加
Enterprise 或 Finance；CLI、API、SDK 不提供 `formats`、`editions`、`geometry`、
`include_text`、`mirror_level` 等普通交付参数。

REST：

```bash
curl -F "file=@document.pdf" http://localhost:8000/v1/parse
curl -F "files=@one.pdf" -F "files=@two.png" http://localhost:8000/v1/tasks
```

入口关系：

- `docmirror.__init__.py` 提供轻量 lazy import 的 `perceive_document`。
- `docmirror/input/pipeline/__init__.py` 是统一 document entry pipeline。
- `docmirror/cli/main.py` 是 Click CLI 根命令。
- `docmirror/__main__.py` 实现 CLI parse 工作流和输出持久化。
- `docmirror/server/api.py` 暴露 FastAPI 路由。

### 6.2 ParsePolicy 与固定交付

所有会改变事实的用户意图都应汇入 `normalize_parse_policy()`，不要在业务代码里重复解析命令参数。worker 数不属于 `ParsePolicy`；输出选择已从公共契约删除。

关键字段：

| 字段 | 说明 |
|---|---|
| `pages` | `1-3,8,10-`、`first:N`、`last:N` 等页码范围 |
| `mode` | `auto`、`fast`、`balanced`、`accurate`、`forensic` |
| `ocr` | `auto`、`force`、`off`、`fallback` |
| `ocr_correction` | `safe`、`suggest`、`off` |
| `ocr_language/country/locale` | OCR 纠错语言和国家地区提示 |
| `ocr_correction_packs` | 显式启用的 opt-in 规则包 ID |
| `page_split` | `auto`、`off`、`force` |
| `doc_type_hint` | 用户给出的 document type hint，可 `prefer` 或 `force` |
| `safety.mode` | `off`、`low`、`medium`、`high` |

交付边界不接收 `formats`、`editions`、`mirror_level`、`geometry` 或
`include_text`。生产 Mirror 固定为 standard 完整事实投影；worker 数与进度回调只影响调度。

注意：

- `mode=fast` 映射到 `enhance_mode=raw`。
- `mode=accurate` 和 `mode=forensic` 映射到 `enhance_mode=full`。
- `ParsePolicy.fingerprint()` 只包含事实选项，用于审计和可重复性，不用于缓存。

### 6.3 FCR 格式路由

FCR 的唯一事实源是：

```text
docmirror/configs/yaml/format_capabilities.yaml
```

解析优先级：

1. 精确 MIME 匹配。
2. MIME prefix 匹配，例如 `image/*`。
3. 最长扩展名匹配，例如 `.tar.gz` 优先于 `.gz`。
4. 回落到 `UNKNOWN_CAPABILITY`。

1.0.0 支持的主要输入：

- PDF：`.pdf`
- 图片：`.png`、`.jpg`、`.jpeg`、`.tiff`、`.tif`、`.bmp`、`.webp`
- OFD：`.ofd`
- Word：`.docx`，`.doc` 经 LibreOffice 转 PDF
- Excel：`.xlsx`、`.csv`，`.xls` 经 LibreOffice 转 XLSX
- PPT：`.pptx`，`.ppt` 经 LibreOffice 转 PDF
- Email：`.eml`，`.msg` 经 `extract_msg` 转 EML
- Web：`.html`、`.htm`，`.mhtml` 内部转 HTML
- Structured：`.json`、`.xml`、`.txt`
- Archive：`.zip`、`.rar`

新增格式时，优先走 FCR，不要在 `ParserDispatcher` 里硬编码。

## 7. 中间件增强管线

MEP 由两个配置驱动：

```text
docmirror/configs/yaml/middleware_catalog.yaml
docmirror/configs/yaml/enhancement_profiles.yaml
```

`middleware_catalog.yaml` 定义中间件类、stage、依赖、启用状态和 `when` guard。`enhancement_profiles.yaml` 按 `content_model` 和 `enhance_mode` 决定实际执行列表。

全局 stage 顺序：

```text
NORMALIZE -> STRUCTURE -> ENRICH -> CLASSIFY -> CONTEXT -> VALIDATE
```

当前主要中间件：

- `LanguageDetector`
- `HeaderInferrer`
- `HeaderAlignment`
- `GenericEntityExtractor`
- `EvidenceEngine`
- `GeometricReconstructor`
- `LlmDocumentRestorer`
- `Validator`
- `AnomalyDetector`，默认关闭，需 `DOCMIRROR_ENABLE_ANOMALY=1`

新增中间件流程：

1. 在 `docmirror/framework/middlewares/<category>/` 下新增实现，继承 `BaseMiddleware`。
2. 在 `middleware_catalog.yaml` 增加 `module`、`class`、`stage`、`provides`、`depends_on`、`when`。
3. 在 `enhancement_profiles.yaml` 的相应 `content_model`/`enhance_mode` 中加入名字。
4. 增加单测和契约测试。
5. 至少运行：

```bash
python3 scripts/validate/validate_middleware_catalog.py
make test-smoke
pytest tests/unit/ -q -k middleware
```

## 8. 输出体系

### 8.1 Mirror JSON vNext

Mirror vNext 是公共 canonical 输出，定义在：

```text
docmirror/models/mirror/vnext.py
docmirror/models/mirror/core.py
docmirror/configs/schemas/mirror.schema.json
```

顶层结构：

```json
{
  "mirror": {},
  "source": {},
  "document": {},
  "pages": [],
  "evidence": {},
  "regions": [],
  "blocks": [],
  "graph": {},
  "semantics": {},
  "quality": {},
  "diagnostics": {},
  "assets": {}
}
```

研发要求：

- 新字段尽量追加，不要破坏现有字段含义。
- 关键业务字段应能追溯到 evidence/source refs。
- `forensic` 层级可以更丰富，`standard` 层级要控制体积。
- 不要把 REST `code/message/data` envelope 混入 Mirror JSON。

### 8.2 Edition 输出

CLI/API 持久化输出由 `write_outputs()` 统一处理：

```text
docmirror/server/edition_outputs.py
docmirror/server/output_builder.py
```

文件 CLI 的默认交付目录：

```text
output/<task_id>/
  001_community.json
  001_content.md
  001_datasets/
    <dataset>.csv
    _audit_cells.csv
```

`--all` 在上述目录中追加 Mirror、Manifest，以及扩展已安装且授权有效时可用的
Enterprise / Finance。Projector 在自身边界完成插件发现与授权检查；未安装、未授权或
不支持当前文档时返回无投影。Writer 不检查包、不检查授权，只写入已经生成的投影。

各 Projector 都只读同一个 `ParseResult`，不能读取 Mirror 投影。默认与 `--all` 模式中的
Community 三件套必须一致。
Manifest 只记录 Projector 的实际结果和已写产物，不重新计算 Edition 可用性，也不记录 requested formats/editions。

### 8.3 按需专用序列化

DMIR 不参与 `build_all_projections()`、REST 普通 sidecar 或默认落盘。它仅由 MCP、PDF-UA 和显式 exporter 调用，从封存后的 `ParseResult` 按需只读序列化。

`docmirror/output/exporters/dispatch.py` 管理这些专用导出格式：

- `json`
- `dmir`
- `markdown`
- `chunks`
- `csv`
- `parquet`
- `html`，当前是占位空输出

Markdown 遵循 [DMP 1.0](markdown_profile_zh-CN.md)。Community Bundle、通用 exporter 和
Mirror vNext exporter 共用 `docmirror/output/markdown_renderer.py`，统一执行阅读流、分页、
上下文转义、复杂表格白名单和图片省略规则。Markdown 只投影源内容与物理表格；领域恢复和
跨页合并后的逻辑数据完整进入 Community JSON/CSV，不重复追加到正文。chunks 继续优先读取
Mirror vNext reading flow。

## 9. 插件与领域能力

### 9.1 Community 6+1

Community 当前核心结构化插件：

- `bank_statement`
- `wechat_payment`
- `alipay_payment`
- `vat_invoice`
- `business_license`
- `credit_report`
- `generic` fallback

标准落盘输出采用 Community Bundle 3.0。Community 插件的“识别”职责在 Canonical Pipeline 中执行，只补充 `ParseResult` 现有的实体、章节、页面、逻辑表与结构化扩展，并在校验和封存前完成；其“投影”职责只读已收敛的 `ParseResult`。系统不创建 Domain Facts 中间模型。`ParseResult` 是唯一内部事实源，Community、Enterprise、Finance 都直接且独立地从它投影，不读取 Mirror 或其他 Edition 的输出。

Community JSON 是可独立交付给上下游系统的完整结构化 API：保持六个顶层块，并在每个 Dataset 的 `rows` 中保存全部业务记录。每条记录至少包含 `record_id`、`normalized`、`canonical_raw`、`raw` 和 `source`。Dataset 必须包含 `completeness`；`row_count`、`emitted_row_count`、`len(rows)` 与对应宽表 CSV 的行数必须守恒，JSON 与 CSV 的 `record_id` 集合和顺序必须相同。任何预览、分页或静默截断都不属于落盘契约。

`001_content.md` 完整保存供人类审查的阅读流和全部物理表格行；每个逻辑数据集同时进入 `001_datasets/<dataset>.csv` 供统计分析，字段级原始值和证据进入 `001_datasets/_audit_cells.csv`。三类产物用途不同，但都来自同一份 `CommunityDataset` 快照。

配置事实源：

```text
docmirror/plugins/<domain>/plugin.yaml
docmirror/plugins/<domain>/resources/domain_contract.yaml
docmirror/plugins/<domain>/resources/scene_keywords.yaml
docmirror/plugins/generic/resources/classification_rules.yaml
```

插件运行时：

```text
docmirror/plugins/_runtime/plugin_registry.py
docmirror/plugins/_runtime/runner.py
docmirror/plugins/_runtime/community/__init__.py
```

### 9.2 插件执行原则

- 插件按 `(domain_name, edition)` 注册。
- Community 插件通过静态 import 注册。
- Enterprise/Finance 插件通过可选包 `docmirror_enterprise`、`docmirror_finance` 注册。
- 插件只能读取封存后的 `ParseResult`，不能读取或修改 Mirror 投影。
- 插件输出先归一为 DEC，再通过 `edition_serializer` 生成 edition JSON。
- post-extract hooks 只能 enrichment edition JSON，不能改变 `ParseResult` 或其他投影。

### 9.3 新增领域插件

最小流程：

1. 在插件清单声明的 `resources/scene_keywords.yaml` 添加 document type 的 include/exclude 关键词。
2. 必要时在所属插件资源中添加分类规则或 category 映射；通用文件归档规则位于 `generic/resources/classification_rules.yaml`。
3. 在插件清单声明的 `resources/domain_contract.yaml` 定义 P0 字段、records、quality、failure 和 gates。
4. 在 `docmirror/plugins/<domain>/community_plugin.py` 实现 `DomainPlugin` 或复用 `BaseTableParser`。
5. 在 `docmirror/plugins/_runtime/community/__init__.py` 静态导入插件。
6. 如果是 community premium 域，在插件自己的 `plugin.yaml` 中声明 `capabilities.premium` 与 `community_order`。
7. 添加 DEC/schema 相关验证和 TQG manifest case。
8. 跑分类、提取、edition schema、证据和失败路径测试。

建议命令：

```bash
python3 scripts/validate/validate_dti.py
python3 scripts/validate/validate_test_manifest.py
pytest tests/contract/ -q -k "domain or edition or plugin"
pytest tests/regression/ -q -m "tier_regression and not tier_slow"
```

## 10. 服务端与 SDK

### 10.1 REST API

服务端入口：

```text
docmirror/server/api.py
```

主要接口：

| Endpoint | 说明 |
|---|---|
| `GET /health` | 健康检查 |
| `POST /v1/tasks` | 创建单文件或多文件任务；`wait=true` 可同步等待 |
| `POST /v1/tasks/batch` | 多文件兼容别名 |
| `GET /v1/tasks/{task_id}` | 查询统一 `TaskResult` |
| `GET /v1/tasks/{task_id}/files/{file_id}/artifacts/{role}` | 按文件与角色下载产物 |
| `POST /v1/parse` | 单文件兼容入口，返回 `TaskResult` |
| `POST /v1/parse/batch` | 多文件兼容入口，返回一个任务结果 |
| `POST /v1/parse/file` | 解析服务端已有文件并返回 `TaskResult` |
| `POST /v1/export/pdfua` | 解析并导出 PDF/UA |

所有解析入口返回精简 `TaskResult`，不返回 Mirror JSON。Community 始终生成；
Enterprise/Finance 仅在相应包已安装、文档类型受支持且许可有效时追加，并通过
`edition_availability.reason` 区分包未安装、未授权、类型不支持或投影失败。

鉴权：

- 设置 `DOCMIRROR_API_KEY` 后启用。
- 支持 `Authorization: Bearer <key>` 或 raw key。
- 未设置时本地服务开放访问。

### 10.2 SDK

SDK 目录：

```text
sdks/typescript/
sdks/go/
sdks/java/
sdks/mcp-server/
```

所有 SDK 应保持四个核心方法一致：

- `parseDocument`
- `parseDocumentBatch`
- `parseFileOnServer`
- `health`

API 合同变更后：

```bash
python scripts/generate_openapi.py
```

然后同步更新各 SDK 的 types/client/README，并按语言运行：

```bash
cd sdks/typescript && npm run build
cd sdks/go && go build ./...
cd sdks/java && mvn compile
cd sdks/mcp-server && npm run build
```

## 11. 配置与环境变量

默认 YAML：

```text
docmirror/configs/yaml/docmirror.yaml
```

运行时配置加载：

```text
docmirror/configs/runtime/settings.py
docmirror/configs/runtime/yaml_loader.py
```

常用环境变量：

| 变量 | 用途 |
|---|---|
| `DOCMIRROR_CONFIG` | 指向自定义 YAML 配置 |
| `DOCMIRROR_API_KEY` | REST API 鉴权 key |
| `DOCMIRROR_LOG_LEVEL` | 日志级别 |
| `DOCMIRROR_MAX_PAGES` | 默认最大页数 |
| `DOCMIRROR_TASK_OUTPUT_DIR` | CLI 默认输出目录 |
| `DOCMIRROR_ENHANCE_MODE` | 默认增强模式 |
| `DOCMIRROR_MIRROR_LEVEL` | CLI 默认 Mirror 输出层级 |
| `DOCMIRROR_MIRROR_CORE_PROFILE` | MirrorCore profile |
| `DOCMIRROR_UDTR_TOPOLOGY_PROFILE` | UDTR 拓扑策略 |
| `DOCMIRROR_UDTR_DETECT_SEALS` | 是否启用印章检测 |
| `DOCMIRROR_ENABLE_ANOMALY` | 是否启用 AnomalyDetector |
| `DOCMIRROR_EXTERNAL_OCR_PROVIDER` | 外部 OCR provider |
| `DOCMIRROR_VLM_PROVIDER` | VLM provider |
| `DOCMIRROR_VLM_MODEL` | VLM model |
| `DOCMIRROR_VLM_API_KEY` | VLM API key |
| `DOCMIRROR_VLM_API_BASE` | VLM API base |
| `OMP_NUM_THREADS` | 限制 OCR/数值库 native 线程 |

## 12. 测试体系

测试目录职责：

| 目录 | 作用 |
|---|---|
| `tests/smoke/` | import、settings、plugin boot 等轻量烟测 |
| `tests/unit/` | 组件级单元测试 |
| `tests/contract/` | MOC/PEC/DEC/API/输出边界契约 |
| `tests/regression/` | TQG manifest-driven 回归门 |
| `tests/integration/` | 冻结 golden 集成回归 |
| `tests/e2e/` | CLI/API/full pipeline |
| `tests/benchmark/` | opt-in 性能/指标 |

常用命令：

```bash
make test-smoke
make test-contract
make test-regression
make test
make test-golden
make coverage
```

PR 级别建议：

```bash
make lint
make test
```

发布候选建议：

```bash
python scripts/run_quality_gate.py --profile full
make validate-release
make validate-vnext-1-0
```

私有 fixtures 说明：

- `tests/fixtures/` 和 `tests/golden/` 默认 gitignored，可能包含敏感真实样本。
- 新同事拿不到私有样本时，优先跑 smoke、unit、contract。
- 涉及真实样本回归时，联系团队获取 fixture 权限。

Community 三件套可使用统一验证程序检查 JSON Schema、完整记录、completeness、CSV
行数与主键顺序、审计 CSV、Markdown DMP 合同。支付流水还可以检查 Markdown 中不存在
被错误渲染成表头的交易记录：

```bash
python3 scripts/validate/validate_community_artifacts.py \
  output/<task_id>/001_community.json \
  --payment-markdown-parity
```

## 13. 改动类型与推荐验证

| 改动类型 | 重点文件 | 推荐验证 |
|---|---|---|
| 新输入格式 | `format_capabilities.yaml`、`input/adapters/` | `validate_format_capabilities.py`、adapter unit、transport contract |
| 新中间件 | `middleware_catalog.yaml`、`enhancement_profiles.yaml` | middleware unit、MEP contract、`make validate-clean` |
| Mirror 字段变化 | `models/mirror/`、schema | mirror contract、UDTR golden、API contract |
| 新领域插件 | `plugins/<domain>/`、scene/domain configs | DTI、DEC、plugin contract、TQG classify/extract/edition |
| 表格逻辑变化 | `tables/`、`ocr/micro_grid/`、相关 plugin | table unit、extract gates、bank/payment regression |
| API 合同变化 | `server/api.py`、`server/schemas.py`、SDK | OpenAPI、SDK build、e2e API tests |
| CLI 输出变化 | `cli/main.py`、`__main__.py`、`edition_outputs.py` | CLI contract、four-file output、artifact manifest |
| Community 三件套变化 | `output/community_bundle.py`、`output/markdown_renderer.py`、Community schema | `test_community_artifact_validator.py`、Community Bundle unit、支付真实样本回归 |
| 发布/打包变化 | `pyproject.toml`、`Dockerfile`、release scripts | `validate_oss_release.py`、wheel smoke、Docker health |

## 14. 质量门与发布

### 14.1 Makefile 入口

| 命令 | 用途 |
|---|---|
| `make install` | 本地 editable 安装全量公开 extras、dev、docs |
| `make format` | ruff format + ruff check fix |
| `make lint` | release-blocking lint 和架构清洁门 |
| `make typecheck` | mypy，全量类型债审计，不作为默认 release blocker |
| `make validate-clean` | import-linter、clean manifest、domain decomposition 等 |
| `make validate-release` | OSS 1.0 发布边界检查 |
| `make smoke-extras` | 公共 optional extras smoke |

### 14.2 run_quality_gate

```bash
python scripts/run_quality_gate.py --list-steps
python scripts/run_quality_gate.py --profile quick
python scripts/run_quality_gate.py --profile standard
python scripts/run_quality_gate.py --profile full
```

profile 含义：

- `hygiene`：死代码、孤儿路径、ruff strict 等。
- `quick`：本地快速循环。
- `standard`：push/PR 前。
- `full`：release candidate。

### 14.3 1.0.0 发布边界

1.0.0 强调：

- 公共定位统一为 Commercial Document Trust Layer / Parse. Prove. Trust.
- `docmirror[all]` 只包含公共 OSS extras。
- 企业/金融包单独分发，不作为 OSS 安装前置条件。
- 公开 quickstart 使用 synthetic artifact，不依赖私有样本。
- docs/design、私有 fixture、credential、本地 plugin state 不进入公开发布。

发布前务必检查：

```bash
python3 scripts/validate/validate_import_purity.py
python3 scripts/validate/validate_oss_release.py
python3 scripts/validate/validate_vnext_1_0_readiness.py
python3 scripts/validate/smoke_optional_extras.py
```

## 15. 安全、隐私与样本

基本原则：

- 不要提交客户原始文件、PII、凭证、license、API key。
- 真实样本放在 gitignored 的 `tests/fixtures/` 或私有数据仓。
- 文档 issue/bug 复现优先用脱敏样本、synthetic 样本或 artifact 片段。
- 对外发布前跑 OSS boundary/release gate。

相关模块：

```text
docmirror/security/
docmirror/security/safety/
docmirror/evidence/redaction.py
docmirror/configs/yaml/privacy_policy.yaml
```

API 部署建议：

- 生产环境设置 `DOCMIRROR_API_KEY`。
- 通过 Nginx/Caddy/Ingress 提供 HTTPS。
- 限制上传文件大小和请求超时。
- OCR 密集 workload 设置 `OMP_NUM_THREADS`，避免 native 库吃满 CPU。

## 16. 常见研发任务

### 16.1 新增一个文件格式

1. 实现 adapter：`docmirror/input/adapters/<format>/<format>.py`。
2. 继承 `BaseParser`，实现 `to_parse_result()`。
3. 在 `docmirror/input/adapters/__init__.py` 导出。
4. 在 `format_capabilities.yaml` 注册 extensions、MIME、transport、content_model、binding。
5. 如果需要外部转换器，配置 `binding.transcode`。
6. 加 unit/contract/e2e 测试。

### 16.2 调整固定交付契约

固定交付契约属于产品级变更，不通过新增普通请求参数扩展。需要新增产物时：

1. 证明产物对所有调用方式都成立，或属于受授权约束的独立 Edition。
2. Projector 必须只读 `ParseResult`，不得依赖 Mirror 或其他 Edition。
3. Writer 只接收已完成的投影并原子写盘。
4. 同步更新 CLI/API/SDK 契约测试与 Manifest schema。

### 16.3 调整 Mirror 投影

1. 先确认字段属于 pages、regions、blocks、graph、semantics、quality 还是 diagnostics。
2. 修改 `models/mirror/` 中的模型和投影逻辑。
3. 更新 `configs/schemas/mirror.schema.json`。
4. 跑 mirror contract、UDTR golden 和 API response 测试。

### 16.4 调整银行流水/支付流水提取

重点目录：

```text
docmirror/plugins/bank_statement/
docmirror/tables/
docmirror/ocr/micro_grid/
docmirror/ocr/local_structure/
docmirror/eval/tqg/
```

建议至少跑：

```bash
pytest tests/unit/ -q -k "bank or table or grid"
pytest tests/contract/ -q -k "mirror or evidence or edition"
pytest tests/regression/ -q -m "track_bank_statement or track_extract"
```

### 16.5 修改 REST API

1. 修改 `docmirror/server/api.py` 和必要的 schema。
2. 同步 `scripts/generate_openapi.py` 生成结果。
3. 更新 TypeScript/Go/Java/MCP SDK。
4. 跑：

```bash
pytest tests/e2e/ -q -k "server or api"
python scripts/generate_openapi.py
cd sdks/typescript && npm run build
cd sdks/go && go build ./...
cd sdks/java && mvn compile
```

## 17. 排障指南

### 17.1 `docmirror doctor` 显示缺依赖

按 capability 安装 extras：

```bash
pip install "docmirror[pdf]"
pip install "docmirror[ocr]"
pip install "docmirror[office]"
pip install "docmirror[server]"
```

### 17.2 `.doc`、`.xls`、`.ppt` 解析失败

这些旧二进制格式依赖 LibreOffice 转换。确认 `soffice` 在 `PATH` 中，或先转成 `.docx`、`.xlsx`、`.pptx`。

### 17.3 扫描件/OCR 质量低

尝试：

```bash
docmirror scan.pdf --mode accurate --ocr force
docmirror scan.pdf --ocr-locale zh-CN --ocr-correction-pack customer.finance
```

纠错策略可选 `safe`（唯一、可验证候选自动应用）、`suggest`（只记录候选）和
`off`（仅基础字符规范化）。纠错摘要位于 Mirror `quality.ocr_correction`，
逐项审计记录位于 `evidence.indexes.ocr_corrections`。

规则包位于 `docmirror/configs/yaml/ocr_correction_packs/`，由 `pack_id`、版本、
优先级、语言/国家/领域范围、精确规则、词库、混淆成本和校验器声明组成。客户私有包
通过环境变量 `DOCMIRROR_OCR_CORRECTION_PACKS` 加载；建议设置 `opt_in: true`，避免
对其他客户请求自动生效。维护和回放命令：

```bash
docmirror ocr check
docmirror ocr packs
docmirror ocr explain "营业牧入" --locale zh-CN --domain financial_report --role field_label
docmirror ocr eval ./golden_samples --fail-on-regression
docmirror ocr export mirror.json review.jsonl
```

新增规则必须同时提供正例、反例和幂等测试。格式校验器只能报告合法性；只有存在可靠
校验算法并得到唯一候选时，`safe` 模式才允许自动改写。

检查：

- `quality_report.json`
- `005_evidence_bundle.json`
- `visual_debug.html`
- Mirror `diagnostics.pipeline`

### 17.4 Enterprise/Finance 输出缺失

检查：

- 是否安装了 `docmirror_enterprise` / `docmirror_finance`。
- license/entitlement 是否满足。
- `manifest.json` 的 `edition_availability`。

### 17.5 测试因 fixtures 缺失而跳过

这是预期行为。公开仓不包含私有样本。需要全量回归时向团队申请 `tests/fixtures/` 和 `tests/golden/`。

## 18. 接手检查清单

新同事接手前建议完成：

- 能本地安装：`pip install -e ".[all,dev,docs]"`。
- 能跑 smoke：`make test-smoke`。
- 能跑 contract：`make test-contract`。
- 能解析 quickstart：`python3 examples/trust_quickstart.py`。
- 能用 CLI 产出 artifact pack。
- 能启动 REST API 并访问 `/health`。
- 理解 FCR、MEP、PEC、Mirror vNext 三条主线。
- 知道私有 fixtures 不在公开仓，不能随意提交样本。
- 改动前能判断自己影响的是 adapter、middleware、Mirror、plugin、server、SDK 还是 release gate。

## 19. 关键参考文件

```text
README.md
README_zh-CN.md
CHANGELOG.md
CONTRIBUTING.md
tests/README.md
scripts/README_quality_gate.md
pyproject.toml
Makefile
docmirror/__init__.py
docmirror/__main__.py
docmirror/cli/main.py
docmirror/input/entry/options.py
docmirror/input/pipeline/__init__.py
docmirror/framework/dispatcher.py
docmirror/framework/base.py
docmirror/framework/orchestrator.py
docmirror/framework/extraction_runner.py
docmirror/server/api.py
docmirror/server/output_builder.py
docmirror/server/edition_outputs.py
docmirror/plugins/_runtime/plugin_registry.py
docmirror/plugins/_runtime/runner.py
docmirror/configs/yaml/format_capabilities.yaml
docmirror/configs/yaml/middleware_catalog.yaml
docmirror/configs/yaml/enhancement_profiles.yaml
docmirror/plugins/<domain>/plugin.yaml
docmirror/plugins/<domain>/resources/domain_contract.yaml
```

维护建议：后续每次大版本迭代时，同步更新本手册的版本基线、核心架构、测试门、输出合同和发布边界。尤其是 Mirror schema、API response、SDK 类型和 edition 输出一旦变动，必须一起更新。
