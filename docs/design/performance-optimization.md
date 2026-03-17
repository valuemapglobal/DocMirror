# 性能优化方向（补充）

在 [Solution Design — G4](solution-design.md#5-性能与资源g4) 已落实 RapidTable 开关与配置的基础上，本文档汇总**当前可进一步优化的性能点**，按收益/成本比与实现难度分类，供迭代时选用。

---

## 1. 已做 / 设计中的优化

| 项 | 状态 | 说明 |
|----|------|------|
| RapidTable 按页数/置信度跳过 | ✅ 已实现 | `DOCMIRROR_TABLE_RAPID_MAX_PAGES`、`DOCMIRROR_TABLE_RAPID_MIN_CONFIDENCE_THRESHOLD` |
| 表提取 Layer 2 并行 | ✅ 已有 | 4 个 char-level 方法用 `ThreadPoolExecutor(max_workers=4)` 并行 |
| 整本 PDF 放入线程执行 | ✅ 已有 | `_process_pdf_sync` 通过 `asyncio.to_thread` 跑，不阻塞事件循环 |
| 缓存按 checksum | ✅ 已有 | 相同内容不重复解析 |
| 布局分析按页并行 | ✅ 已实现 | `analyze_document_layout_parallel` + CoreExtractor 接入；见 [Page Concurrency Implementation](page-concurrency-implementation.md) Phase 1 |
| 大文件 / 页级提取并发 / 按页范围 | 📋 设计中 | 见 solution-design §5.2 D4.1、D4.2；页提取并发规格见同上文档 Phase 2 |

---

## 2. 高收益、可优先考虑的优化

### 2.1 页级并发（大文档吞吐）

- **现状**：`CoreExtractor` 内 `_process_pdf_sync` 对页顺序循环：`analyze_document_layout` 全文档一次、再按页 `_extract_page`，且 `max_page_concurrency=1`，未用多核。
- **瓶颈**：页与页之间除跨页表合并外基本独立，多页文档时 CPU 单核占满，总耗时近似「页数 × 单页耗时」。
- **方向**：
  - **方案 A（进程池）**：每页在独立进程中打开同一 PDF（fitz/open 按页或按需加载），每进程返回该页的 `PageLayout`，主进程再合并、做跨页表合并与后处理。需验证 PyMuPDF/pdfplumber 在多进程下按 path + page_index 打开的可行性与内存。
  - **方案 B（线程池 + 每页 crop）**：主进程持有一份 fitz_doc，每页用 `fitz.open(path)[page_idx]` 在 worker 内再 open 一次（若 fitz 支持按页延迟加载），或主进程 crop 出每页的「字符/线框」数据，worker 只做 table extraction / zone 处理，避免共享可变 doc 对象。
- **配置**：保留 `max_page_concurrency`，当 >1 时启用上述方案之一，并在文档中说明「仅当验证通过后启用，默认 1」。

### 2.2 布局分析：按页并行（已实现）

- **实现**：已提供 `analyze_document_layout_parallel(path, num_pages, max_workers)`，使用 `ProcessPoolExecutor`，每进程 `fitz.open(path)` 后对单页调用 `analyze_page_layout`。CoreExtractor 在 `max_page_concurrency > 1` 且 `num_pages >= 4` 且非图片输入时自动调用。
- **配置**：`DOCMIRROR_LAYOUT_MAX_WORKERS` 可单独限制布局进程数；否则用 `min(max_page_concurrency, cpu_count)`。
- **收益**：多页文档时 layout 阶段耗时近似从 O(n) 降到 O(n/workers)。详见 [Page Concurrency Implementation](page-concurrency-implementation.md)。

### 2.3 OCR DPI 轮次早退

- **现状**：`analyze_scanned_page` 等会做多档 DPI（如 150→200→300），每档都渲染 + 预处理 + OCR，再按词数/质量决定是否升级。
- **优化**：首档 DPI 若词数或质量已达阈值（如 `min_words_final`、质量分），直接返回，不再尝试更高 DPI。当前已有部分「若词数足够则 break」逻辑，可统一为「早退阈值」并在配置中暴露（如 `DOCMIRROR_OCR_EARLY_EXIT_MIN_WORDS`），避免对清晰扫描页多做 300 DPI 轮次。
- **收益**：扫描页占比高时，平均每页少 1～2 次渲染和 OCR 调用。

### 2.4 大文件入口告警与限流

- **现状**：`max_file_size` 已在 Dispatcher 校验；超过后直接失败。
- **优化**：
  - 对超过某阈值（如 50MB）且未超 `max_file_size` 的文件，在 Dispatcher 打 **WARNING** 日志，提示可能高内存与长耗时，便于运维与容量规划。
  - 可选：在配置中增加「大文件策略」：如 `skip_forgery_for_large_file`（超过 N MB 跳过伪造检测以省时间和内存），或仅对前 K 页做 layout/table，后续页仅文本（需与产品约定）。
- **收益**：不改变核心算法即可降低大文件导致的 OOM 与超时风险，并便于定位慢请求。

---

## 3. 中收益、可按需实施的优化

### 3.1 PreAnalyzer 采样与缓存

- **现状**：PreAnalyzer 对文档做一次遍历（采样页 + 首页预览等），结果写入 `metadata["pre_analysis"]`，供 Orchestrator 与 QualityRouter 使用。
- **优化**：若同一文档会被多次解析（如重试、不同 enhance_mode），可考虑在 **进程内** 对 (checksum, enhance_mode) 缓存 PreAnalyzer 结果，避免重复 `analyze`；注意缓存粒度与生命周期，避免内存膨胀。若 Redis 已缓存整份 PerceptionResult，则通常不会重复跑 PreAnalyzer，此项收益主要在「同进程内同文件多次 perceive」场景。

### 3.2 公式识别门控与批量化

- **现状**：每个 formula zone 会走 3 层门控（置信度、面积、数学字符），再决定是否调用 LaTeX 识别；识别为逐 zone 同步调用。
- **优化**：
  - 门控阈值（如 0.65、30% 页面积）已存在，可改为配置项，便于在「速度优先」下调松，减少误入公式识别的 zone。
  - 若公式引擎支持批输入，可先收集本页所有通过门控的 zone 图像，再一次性调用，减少引擎初始化/上下文切换开销（需看 rapid_latex_ocr 等 API 是否支持）。

### 3.3 中间件短路

- **现状**：Orchestrator 按 pipeline_registry 顺序执行所有已配置中间件；部分中间件内部有 `should_skip`。
- **优化**：在「raw 或仅要表格」场景，若未来增加 `enhance_mode=minimal`，可只注册必要中间件（如仅 Validator），减少 EntityExtractor、InstitutionDetector、SceneDetector 等的调用。与现有 `raw` / `standard` / `full` 组合使用即可，无需改中间件内部逻辑。

### 3.4 缓存序列化与 TTL

- **现状**：缓存值为 `PerceptionResult.model_dump_json()`，TTL 固定 24h。
- **优化**：
  - 若结果体量大，可评估是否对 `content.blocks` 做压缩（如 gzip）再写入 Redis，用 content-type 或 key 后缀区分，读取时解压再 `model_validate_json`，以节省内存与网络。
  - TTL 可通过环境变量（如 `DOCMIRROR_CACHE_TTL_SECONDS`）配置，便于不同环境采用不同过期策略。

---

## 4. 低收益或高改造成本

- **整本 PDF 流式/按页加载**：需改 API（如 `page_range`/`page_indices`）与 fitz/pdfplumber 使用方式，设计见 solution-design §5.2 D4.2；实现成本高，适合作为独立项目。
- **替换 OCR/布局/表格引擎**：如换用更快的 OCR 或表格模型，属于技术选型而非小改动，需单独评估。
- **Middleware 并行**：当前中间件存在依赖顺序（如 SceneDetector → EntityExtractor），并行化需要 DAG 调度与结果合并，收益有限且易出错，不建议短期做。

---

## 5. 建议实施顺序

1. **短期**：2.4 大文件 WARNING + 2.3 OCR 早退配置（若尚未完全覆盖）。
2. **中期**：2.2 布局分析按页并行（在确认 fitz 多线程只读安全后）；2.1 页级并发做 PoC（进程池或线程池方案选型）。
3. **按需**：3.1～3.4 在遇到具体瓶颈或需求时再上（如 Redis 内存压力时做 3.4，同文件多次解析时做 3.1）。

---

## 6. 监控与回归

- 在 CI 或生产中对「固定样本集」记录：总耗时、每页平均耗时、内存峰值、各阶段占比（layout / table / OCR / middleware）。便于验证优化效果并防止回退。
- 性能测试与金标可复用 `tests/golden/` 与 `docs/development/testing.md` 中的约定，对耗时/内存加断言或 report-only 门禁。

---

*与 [Solution Design](solution-design.md) §5 配套，侧重「在现有架构下可落地的性能优化点」。*
