# DocMirror Markdown Profile 1.0

DocMirror Markdown Profile（DMP）定义 `*_content.md` 的稳定输出边界。该文件是源文档的
**规范阅读投影**：面向人类阅读、编辑、检索、RAG 和 Agent；它不是视觉复刻、结构化数据库，
也不是 OCR 调试日志。

本文中的“必须”“应该”“可以”分别表示强制要求、推荐要求和可选能力。

## 1. 产物边界

| 产物 | 职责 |
|---|---|
| `*_content.md` | 原文阅读顺序、标题、段落、KV、物理表格 |
| `*_community.json` | 完整结构化 API 数据、章节、数据集全量记录、警告 |
| `*_datasets/*.csv` | 每个逻辑数据集一个宽表，一条业务记录一行 |
| `*_datasets/_audit_cells.csv` | 标准值、原始值与字段级证据审计 |
| `*_mirror.json` | 证据、坐标、血缘、质量和布局 |
| `manifest.json` | 产物清单与校验信息 |

Markdown 不得追加领域推断值、规范化值或跨页合并后的逻辑数据集。需要人类可读的派生摘要时，
应使用独立的 Summary 投影，而不是修改 `content.md` 的源内容语义。

## 2. 文件合同

- 编码必须为 UTF-8，无 BOM，换行必须为 LF，文件末尾必须有一个换行。
- MIME 类型为 `text/markdown; charset=utf-8`。
- 相同 `ParseResult` 必须产生字节级一致的输出；不得写入时间戳、运行 ID 或绝对路径。
- 文件首行必须是 `<!-- docmirror:markdown-profile version="1.0" -->`。
- 每个逻辑页必须以 `<!-- docmirror:page logical="N" source="M" -->` 开始。
- 不使用 YAML Front Matter，不使用水平线模拟分页。
- 默认输出和 `--all` 输出中的同一 `content.md` 必须字节一致。

## 3. 完整性与来源

- 必须使用 `ParseResult.document_flow` 的主阅读流；仅在主阅读流缺失时按页码、reading order、
  bbox 和稳定序号降级。
- 每个进入阅读流的文本证据、KV 和物理表格必须渲染一次，不得预览截断。
- 表格中的内容不得再以普通段落重复；去重依据 evidence identity，不能依据文本字符串。
- `geometric_reconstructor` 产生但不拥有独立 evidence 的便利网格属于派生视图；原始文字存在时，
  Markdown 必须保留原始文字并省略该网格，避免重复消费同一内容。
- 源文件确实重复的页眉、页脚或正文必须保留，因为它们属于不同证据。
- 已批准的确定性 OCR 修正可以进入显示文本；不确定修正、推断字段和标准化值不得进入正文。
- 无法识别的结构必须降级为安全纯文本并保留内容，不能降级为空输出。

## 4. Markdown 子集

DMP 1.0 使用 CommonMark 和 GFM 管道表格。除 DocMirror 命名空间注释外，默认 Community
Markdown 不生成原始 HTML。

- 标题仅在类型化节点确认标题语义时使用 `#` 至 `######`。
- 普通 OCR 行必须合并为自然段；只有具有语义的换行才保留。
- KV 固定渲染为 `**key:** value`。
- 无序列表使用 `-`，有序列表使用数字加句点；不得把普通源文本误解释为列表。
- 类型化代码可以使用 fenced code block；未知普通文本中的反引号必须转义。
- 原始文本中的 Markdown 控制字符必须按段落、标题、KV、表格单元格等上下文分别转义。

## 5. 表格

- 能形成矩形的表格必须使用 GFM 管道表格；`raw_rows` 的存在不是复杂表格判据。
- 所有物理行、空单元格、汇总行和重复表头必须保留，不允许仅输出前若干行。
- 无表头续表使用空表头 GFM，不得把第一条数据提升为表头，也不得虚构列名。
- 表格前的跨列说明行应作为普通 Markdown 文本输出，再输出主体 GFM 表格。
- rowspan/colspan 在阅读投影中展开为矩形：锚点保留文字，被覆盖位置留空；精确几何由 Mirror 保存。
- 单元格内由 PDF 排版造成的软换行必须规范化，不得生成 `<br>`。
- `table`、`thead`、`tbody`、`tr`、`th`、`td`、`caption` 等 HTML 表格标签禁止进入输出。

## 6. 图片与非文本内容

默认 Community 交付固定为 JSON、Markdown 和 CSV，因此 DMP 1.0 禁止 Markdown 图片语法和
`<img>`。装饰图片可以省略；原始图注应作为文本保留；非文本图像的位置可以记录为：

```markdown
<!-- docmirror:nontext type="image" disposition="omitted" -->
```

发生省略时，Community JSON 必须增加信息级 `MARKDOWN_IMAGE_OMITTED` 警告。

只有未来提供正式、可校验的资产交付合同时，后续 DMP 版本才可以允许相对图片链接。远程图片、
绝对本地路径、data URI 和未落地资源始终禁止。

## 7. 页眉、页脚和批注

具有审计价值的页眉、页脚、水印、印章、手写和批注应该以 blockquote 保存，并在前面增加
DocMirror 命名空间注释：

```markdown
<!-- docmirror:region role="watermark" -->
> DRAFT
```

角色值固定为 `header`、`footer`、`watermark`、`stamp`、`handwriting`、`annotation`。

## 8. 安全边界

- OCR、PDF 引擎和外部服务返回的 Markdown/HTML 必须视为不可信源文本。
- 原始 `<div>`、`<span>`、`<img>`、脚本、样式和事件属性不得透传。
- Markdown 图片不得出现；普通链接只有在源文件确实携带链接时才可保留。
- 链接协议仅允许 HTTP、HTTPS 和 mailto；禁止 javascript、data、file 和绝对本地路径。
- DMP 命名空间注释只能由渲染器生成；源文本中的同名注释必须被中和。

## 9. 发布门禁

写盘前必须检查：证据覆盖、证据唯一消费、阅读顺序、表格行列完整、禁止 HTML、图片断链、
确定性和 Markdown 语法。安全降级顺序固定为：

```text
结构化 Markdown → 展平的 GFM 表格 → 安全纯文本 → 记录警告
```

任一 HTML 表格标签、危险属性、Markdown 图片、不可解析引用，或 span 覆盖非空源单元格导致的
内容丢失都属于发布失败，不能静默写盘。

## 10. 实现约束

Community Bundle、通用 Markdown exporter 和 Mirror vNext Markdown exporter 必须调用同一个
DMP 渲染器。任何 adapter 或 edition 不得建立独立的 Markdown 拼接规则。
