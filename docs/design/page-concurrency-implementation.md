# 页级并发与布局并行 — 完整可落地方案

本文档针对「布局分析按页并行」与「页级并发」给出**可直接按步骤实现**的方案：前置条件、接口设计、并发模型、内存与安全约束、分阶段实施与验收标准。

---

## 1. 前置结论（fitz / pdfplumber 安全性与约束）

| 组件 | 线程安全 | 进程安全 | 说明 |
|------|-----------|-----------|------|
| **PyMuPDF (fitz)** | 同一 `Document` 对象**不可**被多线程并发读写 | 每个进程独立 `fitz.open(path)` **安全** | 官方：one Document per thread；多进程下每进程一份 doc 无竞争 |
| **pdfplumber** | 同上，`PDF` 对象非线程安全 | 每进程独立 `pdfplumber.open(path)` **安全** | 与 fitz 一致 |
| **analyze_page_layout(page, page_idx)** | 仅读 `page.rect`、`page.get_text("dict")`、`page.get_drawings()` | 若每进程独立 open 则安全 | 入参为单页，无共享 doc |
| **_extract_page（表/区提取）** | 依赖 `page_plum` / `fitz_page` / 可选 `fitz_doc`（取图） | 每进程/每线程独立 open 则安全 | 不在多线程下共享同一 doc |

**结论**：

- **布局分析并行**：用 **进程池**，每进程 `fitz.open(path)` 取单页后调用 `analyze_page_layout`，仅传 `path` + `page_idx`，无共享 doc，可安全落地。
- **页级提取并行**：用 **线程池** 时，每线程必须 **各自** `fitz.open(path)` 与 `pdfplumber.open(path)`，不能共享同一 doc；线程数需限制（如 4），以控制内存（N 份 doc）。

---

## 2. Phase 1：布局分析按页并行

### 2.1 目标

- 将 `analyze_document_layout(fitz_doc)` 从「单线程顺序遍历每页」改为「多进程按页并行」，主进程只做合并与首页 `is_continuation` 修正。
- 保持对外接口兼容：仍返回 `List[ALPageLayout]`，顺序与 `page_index` 一致。

### 2.2 接口与调用关系

- **新增**（建议放在 `docmirror.core.layout.layout_analysis`）：
  - `_analyze_page_layout_worker(args: Tuple[str, int]) -> Tuple[int, ALPageLayout]`  
    顶层函数，供进程池 pickle。参数 `(path, page_idx)`；内部 `fitz.open(path)` → `analyze_page_layout(doc[page_idx], page_idx)` → `doc.close()` → `return (page_idx, layout)`。
  - `analyze_document_layout_parallel(path: str, num_pages: int, max_workers: int = 4) -> List[ALPageLayout]`  
    使用 `concurrent.futures.ProcessPoolExecutor`，map `_analyze_page_layout_worker` 到 `[(path, 0), (path, 1), ...]`，按 `page_idx` 排序后合并；若 `layouts[0].is_continuation` 则置为 `False`；打与当前 `analyze_document_layout` 同类的日志。
- **现有**：`analyze_document_layout(fitz_doc)` 保留，用于单线程或 `max_workers=1`。
- **CoreExtractor 调用处**（`_process_pdf_sync` 内）：
  - 若 `max_page_concurrency <= 1`：仍调用 `analyze_document_layout(fitz_doc)`。
  - 若 `max_page_concurrency > 1`：调用 `analyze_document_layout_parallel(cleaned_path, len(fitz_doc), max_workers=min(max_page_concurrency, os.cpu_count() or 4))`，不再传 `fitz_doc`（避免跨进程传 doc）。

### 2.3 实现要点

- **可序列化**：`ALPageLayout`、`ContentRegion` 仅含基本类型与 list，保证可 pickle，便于进程间返回。
- **路径**：`path` 必须为绝对路径或主/子进程均可访问的路径，避免工作目录不同导致 open 失败。
- **进程池大小**：`max_workers = min(max_page_concurrency, num_pages, os.cpu_count() or 4)`，避免创建过多进程。
- **异常**：单页失败时可在 worker 内捕获并返回 `(page_idx, None)` 或重抛；主进程对 `None` 可降级为「空 ALPageLayout」或跳过该页并记日志，建议先采用「单页失败则该页返回占位 ALPageLayout + 打 WARNING」以保证列表长度与 `num_pages` 一致，便于后续按 index 使用。
- **Windows**：使用 `ProcessPoolExecutor` 时，worker 会重新 import 模块；`_analyze_page_layout_worker` 必须是模块级函数，且避免在 layout_analysis 模块顶层执行会破坏多进程的代码（如 GUI）。

### 2.4 配置与开关

- 使用现有 `CoreExtractor(max_page_concurrency=N)`；当 `N > 1` 时启用布局并行。
- 可选环境变量：`DOCMIRROR_LAYOUT_MAX_WORKERS`（默认 0 表示用 `max_page_concurrency`），便于单独限制布局阶段并发而不改页级提取并发。

### 2.5 验收标准

- [ ] 多页 PDF（如 20 页）在 `max_page_concurrency=4` 下，`layout_analysis_ms` 明显低于顺序（约 1/workers 量级，考虑进程启动开销）。
- [ ] 返回的 `List[ALPageLayout]` 与顺序实现逐页一致（或仅在预期范围内：如 `is_continuation` 仅首页修正）。
- [ ] 单页或 `max_page_concurrency=1` 时行为与当前完全一致（走 `analyze_document_layout`）。
- [ ] Windows / macOS / Linux 下 pytest 可跑通（至少 unit：传入 path + num_pages 的并行 layout 测试）。

---

## 3. Phase 2：页级提取并发（数字页）

### 3.1 目标

- 在「每页提取」阶段对**数字页**（有 text layer、走 pdfplumber + fitz）做并发，每 worker 独立持有一份 `fitz.open(path)` 与 `pdfplumber.open(path)`，只处理指定 `page_idx`，返回该页的 `PageLayout`（及可选 ocr_text_parts / extraction_layer / confidence）。
- 扫描页（OCR 路径）仍可在主线程顺序执行，或后续再考虑单独并发（依赖 OCR 引擎线程安全）。

### 3.2 约束与取舍

- **_extract_page 依赖**：当前依赖 `self._layout_detector`、`self._formula_engine`、`self._extract_page_styles` 等。若在 worker 内复用这些对象，需保证线程安全（ONNX/模型推理往往不是）；若每线程一份，则内存与初始化成本高。
- **推荐取舍**：在并发路径下，worker **仅做「无模型」提取**：
  - 使用**规则** `segment_page_into_zones(page_plum, page_idx)`，不使用 DocLayout-YOLO。
  - **公式区**：不调用 LaTeX 识别，或仅做「字符流公式抽取」等无模型逻辑；或该页公式块标记为未识别，由后处理统一处理。
  - **样式**：仅用 fitz 取样式，无共享状态即可。
- 这样 worker 只需 `(path, page_idx, layout_al, strategy_params, page_quality, document_page_count)` 等可序列化/可传参数据；若用**线程池**，则直接传 `layout_al` 对象（同进程）；若用进程池，需对 `layout_al` 做 pickle（已满足）。

### 3.3 接口与数据流

- **新增**（建议在 `docmirror.core.extraction` 下）：
  - `extract_single_page_digital(path: str, page_idx: int, layout_al: ALPageLayout, strategy_params: dict, page_quality: float, document_page_count: int, *, use_rule_based_layout_only: bool = True, formula_engine=None) -> Tuple[PageLayout, List[str], str, float]`  
    内部：`fitz.open(path)`、`pdfplumber.open(path)`；取 `page_plum = plum_doc.pages[page_idx]`、`fitz_page = fitz_doc[page_idx]`；若 `use_rule_based_layout_only` 则仅用 `segment_page_into_zones(page_plum, page_idx)` 得到 zones，否则需要传入 layout 模型（暂不实现）；然后按当前 `_extract_page` 的 zone→block、表提取、公式（仅当 formula_engine 非 None）逻辑执行；最后 `doc.close()` 并返回 `(page_layout, ocr_text_parts, extraction_layer, extraction_confidence)`。
- **CoreExtractor 内**：
  - 当 `max_page_concurrency > 1` 且当前页为数字页时，将「该页提取」提交到线程池；worker 调用 `extract_single_page_digital(...)`，传入已并行得到的 `layout_al`。
  - 主进程收集各页 `PageLayout`，按 `page_idx` 排序后，与扫描页结果交错（或先数字页后扫描页），再执行现有 `_merge_cross_page_tables` 与 `_post_process_tables`。
- **线程池**：`ThreadPoolExecutor(max_workers=min(max_page_concurrency, 4))`，每任务 `(path, page_idx, layout_al, ...)`；每线程内 open/close 自己的 fitz 与 pdfplumber，不共享。

### 3.4 内存与限流

- 每线程 1 份 PDF 句柄：`max_workers=4` 即最多 4 份，大文件时需控制 `max_page_concurrency`（如不超过 4 或 8），并在文档中说明「页级并发会成倍增加内存」。
- 可选：在 Dispatcher 或 CoreExtractor 对「文件大小 > 某阈值」时强制将 `max_page_concurrency` 降为 1，避免 OOM。

### 3.5 实现说明（已落地）

- **Worker**：`docmirror.core.extraction.extractor._extract_single_page_digital_worker(args)`，参数元组 `(path, page_idx, layout_al, strategy_params, page_quality, document_page_count)`；线程内 `CoreExtractor(layout_model_path=None)` 且 `_formula_engine = None`，各自 `fitz.open(path)` / `pdfplumber.open(path)`，调用 `_extract_page` 后返回 `(page_idx, page_layout, ocr_parts, extraction_layer, extraction_confidence)`。
- **_extract_page**：当 `self._formula_engine` 为 `None` 时，公式区按文本块输出，不调用 `_crop_zone_image` / `_recognize_formula`。
- **触发条件**：`max_page_concurrency > 1` 且 `plumber_doc` 存在且数字页数 ≥ 2；线程数 `min(max_page_concurrency, 4, len(fitz_doc))`。扫描页仍在主线程顺序执行。

### 3.6 验收标准

- [ ] 多页数字 PDF 在 `max_page_concurrency=4` 下，总提取时间较顺序明显缩短（约 1/workers，受 I/O 与 GIL 影响）。
- [ ] 输出 `pages` 顺序与内容与顺序模式一致（或仅在「无模型」差异：如公式未识别）。
- [ ] 扫描页仍按当前逻辑顺序执行，结果正确。
- [ ] 单页或 `max_page_concurrency=1` 时与当前行为一致。

---

## 4. 实施顺序与依赖

| 阶段 | 内容 | 依赖 | 状态 |
|------|------|------|------|
| **Phase 1** | 布局分析并行：`_analyze_page_layout_worker` + `analyze_document_layout_parallel`，CoreExtractor 在 `max_page_concurrency>1` 且 `num_pages>=4` 时调用 | 无 | ✅ 已实现 |
| **Phase 2** | 从 `_extract_page` 抽离「仅规则+无公式」的 worker，CoreExtractor 对数字页用线程池调用 | Phase 1 已提供并行 `page_layouts_al` | ✅ 已实现 |
| **后续** | 扫描页 OCR 并发（可选）、大文件自动降级 `max_page_concurrency` | Phase 2 | 待实现 |

---

## 5. 配置汇总

| 配置项 | 默认 | 说明 |
|--------|------|------|
| `CoreExtractor(max_page_concurrency=1)` | 1 | 设为 N>1 时：布局用并行；Phase 2 后页提取也用 N 线程 |
| `DOCMIRROR_LAYOUT_MAX_WORKERS` | 0 | 0=用 max_page_concurrency；>0 时仅限制布局阶段进程数 |
| 大文件降级 | 未实现 | 可选：文件 > 50MB 时强制 max_page_concurrency=1 |

---

## 6. 风险与回退

- **进程池**：进程启动有 ~100–500ms 开销，页数很少（如 1–3）时可能更慢，可约定「仅当 `num_pages >= 4` 且 `max_page_concurrency > 1` 时启用布局并行」，否则走顺序。
- **路径**：传入 `analyze_document_layout_parallel` 的 path 必须可靠（建议在调用前 `Path(path).resolve()`）。
- **回退**：设置 `max_page_concurrency=1` 即完全回退到当前顺序行为。

---

*与 [Solution Design](solution-design.md) §5、[Performance Optimization](performance-optimization.md) 配套，作为「页级并发与布局并行」的落地规格。*
