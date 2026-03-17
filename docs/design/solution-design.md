# DocMirror 不足与风险 — 解决方案设计文档

本文档针对《项目深度分析报告》中识别的不足与风险，给出系统化的解决方案设计，包括设计决策、实现要点与验收标准，供迭代开发与评审使用。

---

## 1. 文档概述

### 1.1 目的与范围

| 项目 | 说明 |
|------|------|
| **目的** | 将分析报告中的 7 类不足转化为可执行的设计与实现指引，降低生产环境风险、提升可维护性与可观测性。 |
| **范围** | 格式兼容性、测试与质量保障、错误处理与边界、性能与资源、安全与隐私、文档与 API 一致性、类型与可维护性。 |
| **读者** | 核心贡献者、架构评审、新成员入职。 |
| **非范围** | 不替代具体 Issue/PR 的规格说明；新功能（如流式解析）仅作设计方向，不承诺排期。 |

### 1.2 不足与方案映射

| 编号 | 不足类别 | 对应章节 | 优先级 |
|------|----------|----------|--------|
| G1 | 格式与兼容性 | §2 | P1 |
| G2 | 测试与质量保障 | §3 | P0 |
| G3 | 错误处理与边界 | §4 | P0 |
| G4 | 性能与资源 | §5 | P1 |
| G5 | 安全与隐私 | §6 | P1 |
| G6 | 文档与 API 一致性 | §7 | P2 |
| G7 | 类型与可维护性 | §8 | P2 |

优先级约定：**P0** = 必须在本周期解决；**P1** = 下一周期；**P2** = 技术债，可持续消化。

---

## 2. 格式与兼容性（G1）

### 2.1 问题摘要

- Legacy `.doc` 声称支持但依赖 LibreOffice，未安装时行为未定义；Magic Number 映射表缺少 `.doc`。
- Office 格式（Word/Excel/PPT）的复杂版式、嵌入对象、批注等与 Block 模型的映射未在文档与测试中明确。

### 2.2 设计决策

**D1.1 Legacy .doc 支持策略**

- **选项 A**：将 .doc 从「支持」改为「可选支持」，在文档中明确「需系统安装 LibreOffice 并配置 `soffice` 路径」。
- **选项 B**：在运行时检测 LibreOffice；若不可用，在 `_detect_file_type` 或 Adapter 入口返回明确错误（错误码 `FORMAT_REQUIRES_CONVERTER`），而非静默失败。
- **采纳**：A + B 组合。文档声明可选依赖与环境要求；代码在 WordAdapter 内检测转换器可用性，不可用时快速失败并带上可恢复建议。

**D1.2 文件类型检测完整性**

- 在 `ParserDispatcher._detect_file_type` 的扩展名 `mapping` 中显式增加 `.doc` → `word`。
- 当 Magic Number 与扩展名冲突时（例如扩展名为 .doc 但 Magic 为 PDF），优先信任 Magic Number，并在日志中记录冲突；必要时在 `Provenance` 中增加 `detected_vs_extension` 供审计。

**D1.3 Office 格式能力边界文档化**

- 在 `docs/guide/formats.md` 中为每种 Office 格式增加「能力矩阵」小节：
  - 支持的要素：正文、标题、表格、列表、图片、页眉页脚等。
  - 不支持的要素：OLE 嵌入、复杂批注、修订模式、宏等。
  - 与 Block 类型的对应关系（如 Excel 的 sheet/range → table block）。
- 为 Word/Excel/PPT 各增加至少 1 个「边界用例」测试（如多栏、合并单元格、嵌入表），作为回归基线。

### 2.3 实现要点

- **WordAdapter**：在 `perceive()` 或首次处理 .doc 时调用 `shutil.which("soffice")`（或可配置路径）；若为 .doc 且未找到，在构造 PerceptionResult 时设置 `error.code = "FORMAT_REQUIRES_CONVERTER"`、`error.recoverable = True`，并在 `error.message` 中说明需安装 LibreOffice。
- **Dispatcher**：`mapping` 增加 `".doc": "word"`；在 `_build_failure` 或成功路径的 `provenance.source` 中可选写入 `file_type_detected_by`（`magic` | `extension`）及冲突标记。
- **文档**：在 `getting-started/installation.md` 增加「可选：Legacy .doc 支持」小节，说明安装 LibreOffice 及路径配置。

### 2.4 验收标准

- [ ] README 与 formats 文档中 .doc 支持条件与限制已明确。
- [ ] 扩展名为 .doc 且 Magic 为 MS Office 时，能正确路由到 WordAdapter。
- [ ] .doc 在无 LibreOffice 时返回统一错误码与可恢复建议，且不抛未处理异常。
- [ ] formats.md 包含 Word/Excel/PPT 能力矩阵与 Block 映射说明；各至少 1 个边界用例测试并入 CI。

---

## 3. 测试与质量保障（G2）

### 3.1 问题摘要

- 单测规模相对策略与中间件数量偏少；各 table extraction layer、各 middleware、各 adapter 缺少细粒度单测。
- 缺少「真实样本 + 金标」的回归集与可量化的准确率/F1/表格结构匹配指标。
- CI 中无耗时与内存回归门禁，大文档与高并发行为未固化。

### 3.2 设计决策

**D2.1 测试分层与覆盖目标**

- **L1 单元测试**：每个 table extraction layer（pipe、lines、hline、rect、text、char_*、rapid_table、clustering）至少 1 个「输入 page_plum + 预期 table」的纯函数测试；每个 Middleware 至少 1 个「给定 EnhancedResult → 断言 enhanced_data / status」的测试；每个 Adapter 的 `to_base_result` 或 `perceive` 用最小 fixture（如 1 页 PDF、1 个简单 xlsx）做快照或关键字段断言。
- **L2 集成测试**：保留并扩展 `test_e2e_parse.py`，覆盖「Dispatcher → Adapter → Orchestrator → PerceptionResult」全链路，格式至少包含 pdf、image、word、excel；使用 fixtures 目录下的真实样本，并记录 `status`、`block_count`、`table_count`、`content.text` 长度等可重复指标。
- **L3 回归与金标**：引入「金标数据集」目录（如 `tests/golden/`），目录结构按格式与场景分类；每个样本附带 `expected.json`（或 `expected.yaml`）描述最小断言（如表格行数、关键实体键存在性）；CI 中运行 golden 测试并对比，差异需显式 approve 或更新 expected。

**D2.2 金标数据与指标**

- 金标样本不进入主仓库大文件时，使用 Git LFS 或 CI 从外部存储下载；仓库内保留 `tests/golden/README.md` 说明每类样本的用途与预期指标。
- 定义 2～3 个可自动计算的「文档级指标」：例如表格结构一致率（header + 行数列数）、关键实体存在率、Validator 的 l2_score 分布；在 CI 的 golden 运行后输出 summary（如 `table_match_rate >= 0.95`），门禁可选（先 report-only，再逐步设阈值）。

**D2.3 性能与资源门禁**

- 在 CI 中增加可选 job（如 `ci-performance`）：对固定的一组「小/中/大」PDF 与图片，运行 `perceive_document`，记录总耗时与峰值内存；输出为 artifact；门禁策略可为「不超过基线 1.5x」或「P95 耗时 < 某值」，基线由历史运行结果确定并存储在仓库或 CI 变量中。
- 大文档与高并发：在 `tests/` 下增加 `test_concurrent_parse.py`（如 5 个并发任务），断言无死锁、无 OOM、所有结果 status 为 success 或 partial；可标记为 `@pytest.mark.slow` 并在默认 CI 中跳过，由 cron 或手动触发。

### 3.3 实现要点

- **目录结构建议**：
  - `tests/unit/table/`：按 layer 或策略文件组织 table 单测。
  - `tests/unit/middlewares/`：按中间件名称组织。
  - `tests/unit/adapters/`：按格式组织。
  - `tests/golden/`：按 `pdf/`、`image/`、`word/` 等分子目录，每样本一个子目录，内含源文件 + `expected.json`。
- **金标断言**：使用小型 DSL 或 JSON schema 描述 expected（如 `{"tables": [{"min_rows": 2, "header_contains": ["日期"]}], "entities": ["account_holder"]}`），由 pytest fixture 加载并做宽松匹配（存在性、最小值），避免对具体文本的强绑定。
- **CI 配置**：在 `.github/workflows/ci.yml` 中增加 `tests-golden` 与可选的 `tests-performance` job；性能 job 使用 `pytest --benchmark` 或自定义 timing 输出。

### 3.4 验收标准

- [ ] 每个 table extraction layer 至少有 1 个单测；每个 Middleware 至少有 1 个单测；每个 Adapter 至少有 1 个集成级测试。
- [ ] `tests/golden/` 存在且至少包含 2 种格式（如 pdf + image）各至少 1 个样本及 expected 描述；CI 中 golden 测试可运行并通过。
- [ ] CI 中可选性能 job 存在，能产出耗时/内存报告；并发测试存在且通过（可标记 slow）。
- [ ] 文档 `docs/contributing.md` 或新文档 `docs/development/testing.md` 中说明测试分层、如何添加金标样本与如何运行性能测试。

---

## 4. 错误处理与边界（G3）

### 4.1 问题摘要

- 大量 `except Exception: logger.debug(...)` 导致静默降级，难以排查；缺少结构化错误码与可恢复/不可恢复区分。
- 「无表格」在纯文本文档中为正常情况，与「解析失败」混用 status/error 易误解。
- PDF 整本失败时无「仅文本 / 仅图片」的降级策略说明。

### 4.2 设计决策

**D3.1 统一错误码与可恢复性**

- 在 `docmirror/core/exceptions.py`（或新建 `docmirror/models/errors.py`）中定义 **错误码枚举** 与 **可恢复性** 规则，供 PerceptionResult.error 与 API 使用：
  - 示例：`FILE_NOT_FOUND`、`FILE_TOO_SMALL`、`FILE_TOO_LARGE`、`UNSUPPORTED_FORMAT`、`FORMAT_REQUIRES_CONVERTER`、`EXTRACTION_FAILED`、`ORCHESTRATION_FAILURE`、`ENCRYPTED_PDF`、`TIMEOUT` 等。
  - 每个错误码对应 `recoverable: bool` 与建议的 `user_message` 模板（可被 i18n 替换）。
- 在 `ErrorDetail` 中强制使用 `code: str`（来自枚举），保留 `message` 为详细技术信息；对外 API 可使用 `user_message` 或根据 code 生成。

**D3.2 区分「无表格」与「解析失败」**

- 引入或复用 **解析意图 / 文档类型** 信号：例如 PreAnalyzer 的 `content_type`（`table_dominant` / `text_dominant` / `mixed`）。
- 规则：当 `content_type != "table_dominant"` 且 `table_count == 0` 时，不将 status 降级为 partial，也不注入 "No tables found" 类 error；仅当 `table_dominant` 且 table_count 为 0 时，才设为 partial 并记录该 error。
- 可选：在 PerceptionResult 或 diagnostics 中增加 `expect_tables: Optional[bool]`，由 PreAnalyzer 或 SceneDetector 写入，供上游判断。

**D3.3 降级策略文档与可选实现**

- 在 `docs/guide/configuration.md` 或新文档 `docs/guide/error-handling.md` 中明确：
  - 当前行为：PDF 主路径失败时返回失败结果；无自动「仅文本」或「仅图片」降级。
  - 可选策略（设计层）：支持配置项如 `fallback_on_full_failure: "text_only" | "none"`，在 Dispatcher 或 PDFAdapter 内，当主 pipeline 失败时尝试仅提取文本（如 fitz get_text）并返回 partial 结果；实现可放在后续迭代。
- 代码中在关键路径（如 Orchestrator.run_pipeline、Dispatcher.process）将「已知业务异常」与「未知异常」区分：已知异常映射到错误码并设置 recoverable；未知异常记录为 `ORCHESTRATION_FAILURE` 或 `EXTRACTION_FAILED`，并记录 traceback 到日志，避免裸 `except Exception` 吞掉。

### 4.3 实现要点

- **错误码模块**：例如 `DocMirrorErrorCode` 枚举 + `ERROR_META: Dict[str, {recoverable, user_message_template}]`；`_build_failure` 与 Adapter 内统一使用该模块生成 `ErrorDetail`。
- **Orchestrator**：在「无 table_blocks 且 status == success」的当前逻辑前，增加对 `pre_analysis.content_type` 或 `result.enhanced_data.get("expect_tables")` 的判断；仅当期望有表且无表时才降级并添加 error。
- **日志**：对静默吞掉的异常，至少在使用 `logger.debug` 时包含 `exc_info=True` 一次（或使用 `logger.exception` 在 WARNING 级别），便于排查；同时保证不因日志量影响生产，可通过 `DOCMIRROR_LOG_LEVEL` 控制。

### 4.4 验收标准

- [ ] 存在统一错误码定义与 ErrorDetail 的 code/recoverable 使用规范；所有 `_build_failure` 及主要 Adapter 失败路径使用该规范。
- [ ] 「无表格」仅在 table_dominant 场景下导致 partial + error；纯文本文档无表时仍为 success。
- [ ] 文档中已说明当前失败行为与可选降级策略（含未来设计）；关键路径无裸 `except Exception` 静默吞掉（至少带 exc_info 或 exception 日志）。

---

## 5. 性能与资源（G4）

### 5.1 问题摘要

- 页级并发默认 1，大文档无法利用多核；整本 PDF 加载到内存，超大文件存在 OOM 风险。
- RapidTable 约 10s/页，无按页数或质量跳过该层的配置。

### 5.2 设计决策

**D4.1 页级并发与线程安全**

- **现状**：`CoreExtractor` 使用共享 fitz/pdfplumber 文档，多线程写同一对象不安全，故 `max_page_concurrency=1`。
- **方向**：在「每页独立读取」的前提下支持并发：即对每一页用 `fitz.open(path)[page_idx]` 或等价方式在 worker 内打开页面数据，避免共享同一 Document 对象写；或使用进程池（每进程独立 open）以隔离 GIL，代价为序列化与内存复制。优先方案为「线程池 + 每页按需 crop 或按页 open」的可行性验证；若依赖 pdfplumber 的 `pages[i]` 必须来自同一 `open()`，则文档中明确「当前设计为单线程页处理，大文档耗时随页数线性增长」。
- **配置**：保留 `max_page_concurrency`，当 >1 时仅在实现验证通过后启用；否则忽略并打 WARNING 日志，避免静默错误行为。

**D4.2 大文件与内存**

- **短期**：在文档与配置中明确 `max_file_size`（当前 500MB）的语义，并建议对超大 PDF 先做「页范围」或「页采样」预处理（业务侧）；在 Dispatcher 中对超过某阈值（如 50MB）的文件打 WARNING 日志，提示可能的高内存占用。
- **中期**：设计「流式/按页加载」接口：例如 `perceive_document(path, page_range=(1, 10))` 或 `perceive_pages(path, page_indices=[0,1,2])`，仅打开指定页并返回该子集的 PerceptionResult；实现时需保证 fitz/pdfplumber 按页打开或按需加载，避免整本加载。

**D4.3 RapidTable 与策略开关**

- 在 `docmirror/configs/settings.py` 或表提取相关配置中增加：
  - `table_rapid_max_pages: Optional[int]`：当文档页数超过该值时，跳过 RapidTable 层（或仅对前 N 页启用）。
  - `table_rapid_min_confidence_threshold: float`：仅当上游 layer 返回的 confidence 低于该值时才尝试 RapidTable；默认 0.3。
- 在 `extract_tables_layered` 中读取上述配置（或通过 `strategy_params` 传入），在进入 L2.5 前判断；若跳过，在 `_layer_timings_var` 或 metadata 中记录 `rapid_table_skipped: reason`。

### 5.3 实现要点

- **配置项**：在 `DocMirrorSettings` 或 table 专用配置中增加 `table_rapid_max_pages`、`table_rapid_min_confidence_threshold`；通过环境变量 `DOCMIRROR_TABLE_RAPID_MAX_PAGES` 等注入。
- **extract_tables_layered**：在调用 `_extract_by_rapid_table` 前，若 `page_count > table_rapid_max_pages` 或上游 `confidence >= table_rapid_min_confidence_threshold`，则跳过并记录。
- **文档**：在 configuration 中说明上述两个参数及「大文档建议」；在 architecture 或 performance 小节说明当前页处理为顺序模型及原因。

### 5.4 验收标准

- [ ] `table_rapid_max_pages` 与 `table_rapid_min_confidence_threshold` 已存在且生效；超过页数或高于置信度时 RapidTable 被跳过并有日志或 metadata 记录。
- [ ] 文档中已说明 `max_file_size`、大文件风险与可选「页范围」使用方式；若已实现 `page_range`/`page_indices`，则文档与 API 一致。
- [ ] 若页级并发已实现，CI 或文档中说明使用条件与限制；否则文档中明确当前为顺序页处理。

---

## 6. 安全与隐私（G5）

### 6.1 问题摘要

- Redis 缓存 key 含 checksum，同一文件不同路径会共享缓存；缓存语义需在文档中说明。
- 伪造检测元数据黑名单可能将正常导出判为可疑，需可配置或明确「仅供参考」的定位。

### 6.2 设计决策

**D5.1 缓存语义与路径**

- **语义**：缓存 key = `checksum + document_type`，即「内容相同则共享结果」，与文件路径无关。在 `docs/guide/configuration.md` 与 `docs/guide/architecture.md` 的缓存小节中明确写出：
  - 相同内容（SHA256）不同路径会命中同一缓存；
  - 若业务需要「同内容不同来源」区分，应在调用方使用不同的 `document_type` 或不在该场景使用缓存。
- **可选**：在 `parse_cache.set/get` 的 key 中支持可选前缀（如 `prefix + checksum`），由调用方传入租户或来源标识；默认前缀为空，保持现有行为。

**D5.2 伪造检测可配置与定位**

- **黑名单可配置**：将 `forgery_detector` 中的 `_SUSPICIOUS_METADATA_LOWER` 改为从配置或环境变量加载（如 `DOCMIRROR_FORGERY_METADATA_BLACKLIST`，JSON 数组）；若未设置则使用当前默认列表；允许部署方覆盖或清空以降低误报。
- **文档定位**：在 `docs/guide/configuration.md` 与 API 响应中说明：伪造检测结果为「辅助参考」，不构成法律或合规结论；并说明哪些元数据会触发、如何配置黑名单。
- **结果字段**：保持 `is_forged`、`forgery_reasons`；在 Provenance 或 Validation 中可增加 `forgery_detection_note: Optional[str]`，用于放置「本结果仅供参考」等说明（可由配置注入）。

### 6.3 实现要点

- **配置**：在 `DocMirrorSettings` 或 security 专用配置中增加 `forgery_metadata_blacklist: List[str]`，从 env 的 JSON 字符串解析；`forgery_detector` 使用该列表而非硬编码常量。
- **文档**：在 configuration 中新增「缓存」与「安全与伪造检测」小节；在 API 文档或 PerceptionResult 说明中注明 trust/validation 的用途与限制。
- **缓存 key**：若实现前缀，在 `framework/cache.py` 的 `get/set` 签名中增加 `key_prefix: str = ""`，并文档化。

### 6.4 验收标准

- [ ] 缓存 key 语义（内容相同即共享、与路径无关）及可选前缀（若实现）已在文档中说明。
- [ ] 伪造检测元数据黑名单可配置；未配置时行为与当前一致。
- [ ] 文档与 API 中已明确伪造检测的「仅供参考」定位及配置方式。

---

## 7. 文档与 API 一致性（G6）

### 7.1 问题摘要

- `enhance_mode` 的 `full` 与 `standard` 差异未在代码或文档中写清；Builder 通过 shim 导入，长期应统一入口。

### 7.2 设计决策

**D6.1 enhance_mode 语义**

- 在代码中确认并固定语义：
  - `raw`：仅 CoreExtractor，无中间件。
  - `standard`：SceneDetector + EntityExtractor + InstitutionDetector + Validator（及当前 pipeline_registry 中为该模式配置的其它中间件）。
  - `full`：若与 standard 当前实现相同，则文档中写「full 与 standard 当前等价，保留 full 供未来扩展（如更多中间件或 LLM 增强）」；若已有差异，在 `_build_middlewares` 或 `get_pipeline_config` 中明确列出 full 的额外中间件，并在文档中列出。
- 在 `docs/guide/configuration.md` 中增加「增强模式」小节：表格列出 raw / standard / full 的差异（中间件列表、典型用途、性能影响）。

**D6.2 Builder 与 PerceptionResult 导入**

- 推荐统一从 `docmirror.models` 对外暴露：`from docmirror.models import PerceptionResult, PerceptionResultBuilder`（在 `models/__init__.py` 中从 `construction.builder` 再导出 `PerceptionResultBuilder`）。
- 内部与 Adapter 逐步改为 `from docmirror.models import PerceptionResultBuilder` 或 `from docmirror.models.construction.builder import PerceptionResultBuilder`；弃用 `from docmirror.models.builder import ...` 的 shim，或在 deprecation 周期内保留并打 DeprecationWarning。
- 在 contributing 或开发文档中说明「新代码请从 `docmirror.models` 导入模型与 Builder」。

### 7.3 实现要点

- **pipeline_registry**：检查 `get_pipeline_config(..., "full")` 与 `"standard"` 的返回值；若一致，在代码注释与文档中说明「full 目前等价 standard」。
- **models/__init__.py**：添加 `PerceptionResultBuilder` 的导出；在 `docmirror/__init__.py` 中如需对外也可导出。
- **文档**：configuration 中增加 enhance_mode 表格；API 或 architecture 中说明推荐导入路径。

### 7.4 验收标准

- [ ] 文档中明确列出 raw / standard / full 的差异（或声明 full 与 standard 当前等价）。
- [ ] `PerceptionResultBuilder` 可从 `docmirror.models` 导入；旧 `models.builder` 路径有弃用说明或 DeprecationWarning，并在文档中标注推荐导入方式。

---

## 8. 类型与可维护性（G7）

### 8.1 问题摘要

- mypy 使用 `ignore_missing_imports = true`，可选依赖与第三方缺少 stub，类型安全主要靠约定；domain 模型（dataclass）与 Pydantic（PerceptionResult）两套，演进时需同步 Builder。

### 8.2 设计决策

**D7.1 类型与 mypy**

- **短期**：对核心公共 API（如 `perceive_document`、`PerceptionResult`、`BaseParser.perceive`）保证类型注解完整；在 CI 中对 `docmirror/` 运行 mypy，仅对已标注模块严格（可先排除 `**/ocr/**` 等重度依赖可选包的路径）。
- **中期**：为可选依赖（如 rapidocr、pdfplumber、fitz）在 `py.typed` 或 stub 目录中提供最小 stub（仅用到的签名），或使用 `types-*` 若存在；逐步将 `ignore_missing_imports` 改为按包或按目录关闭。

**D7.2 模型演进与 Builder 同步**

- 在 `docs/development/` 或 contributing 中增加「模型变更清单」：
  - 修改 `Block`、`PageLayout`、`BaseResult` 等 domain 模型时，必须同步检查 `PerceptionResultBuilder.build` 与 `_map_block` 及所有产出 `ContentBlock` 的路径。
  - 修改 `PerceptionResult`、`ContentBlock`、`DocumentContent` 等 Pydantic 模型时，必须同步检查 Builder 与 Dispatcher 的 `_build_failure`、cache 的序列化。
- 在关键 Builder 函数上增加单元测试：给定最小 BaseResult + EnhancedResult，断言生成的 PerceptionResult 的 `content.blocks` 数量与类型、必要字段非空；domain 或 Pydantic 变更时跑该测试以发现断裂。

### 8.3 实现要点

- **mypy**：在 `pyproject.toml` 或 `mypy.ini` 中配置 `files = docmirror`，对指定子包不使用 `ignore_missing_imports`（或使用 `[[tool.mypy.overrides]]` 按路径区分）；CI 中增加 `mypy docmirror` 步骤。
- **文档**：在 contributing 中增加「模型与 Builder 变更检查清单」；列出 Builder 单测文件，并说明新增 Block 类型或 ContentBlockType 时需更新的位置。

### 8.4 验收标准

- [ ] 至少对 `framework/`、`models/`、公共 `__init__.py` 运行 mypy 且无新增错误；可选依赖可仍 ignore，但需有清单说明。
- [ ] 存在「模型变更检查清单」文档；Builder 有单测覆盖 `_map_block` 或 `build` 的典型输入，且 CI 通过。

---

## 9. 实施路线图

### 9.1 阶段划分

| 阶段 | 目标 | 建议周期 | 主要交付 |
|------|------|----------|-----------|
| **Phase 0** | 风险与可观测性 | 1～2 周 | 错误码与「无表格」逻辑（§4）；enhance_mode 与缓存/伪造检测文档（§6、§7）；Builder 导入统一（§7）。 |
| **Phase 1** | 质量与测试基线 | 2～3 周 | 测试分层与单测补充（§3）；金标目录与 CI golden job（§3）；格式与 .doc 行为与文档（§2）。 |
| **Phase 2** | 性能与资源可控 | 2 周 | RapidTable 开关与配置（§5）；大文件与缓存语义文档（§5、§6）；可选性能/并发 CI job（§3）。 |
| **Phase 3** | 长期可维护性 | 持续 | mypy 严格化与模型变更清单（§8）；页级并发或 page_range 设计/实现（§5）；流式或按页加载的进一步设计。 |

### 9.2 依赖关系

- §4（错误处理）与 §7（enhance_mode/导入）无前置依赖，可立即开工。
- §3（测试）可为 §2、§4、§5 的改动提供回归保护，建议与 Phase 0 并行启动部分单测。
- §5 的 RapidTable 配置与 §3 的性能 job 可并行；§5 的页级并发或 page_range 依赖设计评审后再实现。

### 9.3 评审与迭代

- 本设计文档应在每个 Phase 结束前做一次「实现 vs 设计」对照评审，更新验收状态与未决项。
- 新发现的不足或风险可追加到本文档「不足与方案映射」表，并对应新增章节或修订现有章节。

---

## 10. 附录

### A. 错误码建议列表（初版）

| Code | recoverable | 典型场景 |
|------|-------------|----------|
| `FILE_NOT_FOUND` | 否 | 路径不存在 |
| `FILE_TOO_SMALL` | 否 | 小于 min_file_size |
| `FILE_TOO_LARGE` | 否 | 大于 max_file_size |
| `UNSUPPORTED_FORMAT` | 否 | 无法识别的格式 |
| `FORMAT_REQUIRES_CONVERTER` | 是 | .doc 需 LibreOffice |
| `EXTRACTION_FAILED` | 视情况 | 核心提取异常 |
| `ORCHESTRATION_FAILURE` | 否 | 管道未捕获异常 |
| `ENCRYPTED_PDF` | 是 | 需密码的 PDF |
| `TIMEOUT` | 是 | 超时（若未来支持） |

### B. 金标 expected 最小结构示例（JSON）

```json
{
  "version": 1,
  "assertions": {
    "status": ["success", "partial"],
    "table_count": { "min": 1 },
    "tables": [
      { "min_rows": 2, "header_contains_any": ["日期", "交易日期"] }
    ],
    "entities_required": ["account_holder", "account_number"]
  }
}
```

### C. 文档变更清单（随实现更新）

- [ ] `docs/guide/configuration.md`：增强模式、缓存、伪造检测、RapidTable/大文件相关配置。
- [ ] `docs/guide/formats.md`：.doc 支持条件、Office 能力矩阵与 Block 映射。
- [ ] `docs/guide/error-handling.md`（新建）：错误码、可恢复性、降级策略。
- [ ] `docs/guide/architecture.md`：缓存 key 语义、可选 key_prefix。
- [ ] `docs/getting-started/installation.md`：Legacy .doc 与 LibreOffice。
- [ ] `docs/development/testing.md`（新建）：测试分层、金标、性能测试说明。
- [ ] `docs/contributing.md` 或开发文档：模型变更清单、推荐导入路径、mypy 范围。

---

*文档版本：1.0 | 与《DocMirror 项目深度分析报告》不足与风险一一对应，可作为迭代与评审依据。*
