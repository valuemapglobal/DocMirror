# 无框线表格隐式网格重建

**日期：** 2026-06-24  
**范围：** Mirror 层物理表格重建，尤其是无框线流水类表格  
**参考样例：** 江苏银行对公账户对账单，10 个物理列，91 条逻辑交易行

## 1. 问题定义

无框线表格在 PDF 中没有显式的横线、竖线或单元格边框。朴素解析器只能看到带坐标的字符或词块，
因此很容易把一条逻辑交易记录误识别成多条物理文本行，或者把相邻的物理列合并进同一个单元格。

例如，下面这个银行流水表头在版面上是 10 列物理表格：

```text
序号 | 交易日期 | 交易时间 | 摘要 | 凭证种类 | 借方发生额 | 贷方发生额 | 余额 | 对方账户 | 对方户名
```

Mirror 层必须先忠实保留这 10 个物理列。领域插件后续可以把这些物理列映射成更少的标准语义字段，
但语义映射不能反过来压扁 Mirror 层的表格几何结构。

## 2. 第一性原理

表格本质上是页面文本的二维隐式分区：

- 列是一个垂直区间，在多行中反复承载同类角色的文本。
- 行是一个水平带，一条行带承载一条完整记录，即使这条记录在视觉上被渲染成多条物理文本线。
- 单元格是一个列区间和一个行带的交集。
- 正确的表格重建应最大化守恒：每个可见表格 token 都应被分配到唯一单元格中，除非它是页码、
  页脚等明确的页面附属元素。

对于无框线表格，线条检测不可用，因此可靠证据主要来自：

- 表头锚点：稳定列名，例如 `交易日期`、`借方发生额`、`对方账户`。
- 记录锚点：稳定的新记录起始信号，例如序号、日期、时间。
- 数据类型锚点：日期、时间、金额、余额、长账号、对方户名。
- 负空间：不同角色之间反复出现的空白区间。
- 跨行一致性：同一个 x 区间在多行中应接收同类数据。

因此，算法按以下顺序恢复网格：

1. 检测表格区域。
2. 基于表头锚点恢复物理列边线。
3. 基于记录起始锚点恢复逻辑行带。
4. 按字符中心点把字符分配进单元格。
5. 用逻辑行质量而不是物理文本行数量为候选表格评分。

## 3. 核心算法

### 3.1 输入

算法工作在页面级字符流上：

```python
Char = {
    "text": str,
    "x0": float,
    "x1": float,
    "top": float,
    "bottom": float,
}
```

`pdfplumber.extract_words()` 产生的词框只用于表头锚定。单元格分配仍以字符框作为事实来源。

### 3.2 表头锚点检测

1. 根据字符高度估计主导字号。
2. 用 CJK 自适应容差提取词：
   - `x_tolerance = max(3, font_size * 0.9)`
   - `y_tolerance = max(3, font_size * 0.4)`
3. 将词按 y 坐标聚合成水平行。
4. 用领域表头词表给前 N 行打分。
5. 选择得分最高的行，并要求至少命中 3 个表头词。

这一步会把多字中文表头保留为完整词，避免 `借方发生额` 被拆成单字或碎片后导致列边界失真。

### 3.3 列边线恢复

假设表头词按 x 坐标排序为：

```text
H0, H1, ..., Hn-1
```

列边线定义为：

```text
D0 = 根据首个表头和页面文本范围推断出的左边界
Di = midpoint(H{i-1}.x1, H{i}.x0), 其中 1 <= i < n
Dn = 根据最后一个表头和页面文本范围推断出的右边界
```

物理表格有 `n` 列和 `n + 1` 条竖向分隔线。

关键不变量：

```text
len(dividers) == len(headers) + 1
```

在江苏银行样例中，这一步恢复出 10 列：

```text
序号, 交易日期, 交易时间, 摘要, 凭证种类, 借方发生额, 贷方发生额, 余额, 对方账户, 对方户名
```

### 3.4 物理文本线聚合

表头下方的字符按自适应 y 容差聚合为物理文本线：

```text
y_tolerance = clamp(median_char_height * 0.6, 1.5, 5.0)
```

每条物理文本线按字符中心点分配到已经恢复的列区间：

```text
column_index = i where dividers[i] <= (char.x0 + char.x1) / 2 <= dividers[i + 1]
```

这里刻意使用字符中心，而不是词中心。这样可以拆开视觉上粘在一起的字符串，例如：

```text
7065018800020镇江东翔网络科
```

可以被拆成：

```text
对方账户 = 7065018800020
对方户名 = 镇江东翔网络科
```

### 3.5 逻辑行带恢复

物理文本线不一定等于逻辑表格行。一条银行交易记录可能渲染成：

```text
第 1 条物理线：序号 / 日期 / 时间 / 对方账户前半 / 对方户名前半
第 2 条物理线：摘要 / 借方或贷方 / 余额 / 对方账户后半 / 对方户名后半
第 3 条物理线：对方户名尾部
```

当一条物理线包含新记录起始锚点时，算法创建新的逻辑行：

- 日期：`YYYY-MM-DD`、`YYYY/MM/DD` 或紧凑格式 `YYYYMMDD`
- 时间：`HH:MM` 或 `HH:MM:SS`
- 第一列中的序号
- 前若干锚点列中至少两个非空

从当前起始线到下一条起始线之前的所有物理线，都合并到当前逻辑行中。

单元格合并规则：

- 相邻数字碎片直接拼接，不加空格。
- 相邻中文碎片直接拼接，不加空格。
- 其他碎片之间加入一个空格。
- `第1页` 这类纯页脚行在合并前丢弃。

这一步恢复的就是横向行边线：

```text
row_band_k = [start_y_of_record_k, start_y_of_record_{k+1})
```

最后一条记录的下边界，是表格区域内最后一条非页脚物理线的底部。

### 3.6 候选验证

重建出的网格只有满足以下条件时才被接受：

- 表头行至少命中 3 个词表项。
- 分隔线数量等于表头数量加一。
- 至少恢复出一条逻辑数据行。
- 大多数逻辑行至少有两个非空单元格。

当表头锚定失败时，旧的投影间隙聚类算法仍作为 fallback 保留。

## 4. 候选选择

无框线页面通常会产生多个候选：

- `header_guided`：列数可能正确，但仍然是物理文本线级别的行。
- `x_clustering`：行数很多，但常见问题是行碎片化、列合并。
- `grid_reconstructor`：同时恢复物理列和逻辑行。
- `signal_processor`：部分场景有效，但对多行流水较弱。

原始行数不是可靠质量信号。一个碎片化候选可能有 100 条物理文本线，而正确表格只有 31 条逻辑交易行。

对于无框线流水，最佳候选选择应通过逻辑行质量来评估行数量：

```text
effective_rows = raw_rows * logical_row_quality
```

`logical_row_quality` 从数据行中估计：

- 强信号：同一行同时包含日期和金额。
- 次级信号：行内非空列密度足够高。
- 惩罚：如果少于 25% 的行满足日期+金额闭合，则密度 fallback 减半。

这样可以避免碎片化物理行候选仅凭“行数更多”击败正确的逻辑网格。

## 5. 伪代码

```python
def reconstruct_borderless_grid(page):
    chars = visible_non_watermark_chars(page)
    header_words, header_y = find_best_header_row(page, chars)
    headers = [w.text for w in header_words]

    if vocab_score(headers) < 3:
        return fallback_projection_grid(chars)

    dividers = column_dividers_from_header_words(header_words, chars)
    if len(dividers) != len(headers) + 1:
        return fallback_projection_grid(chars)

    physical_lines = group_chars_by_y(chars, below=header_y)
    logical_rows = []
    current = None

    for line in physical_lines:
        cells = assign_chars_by_center(line, dividers)

        if is_footer(cells):
            continue

        if is_record_start(cells, headers):
            if current:
                logical_rows.append(current)
            current = empty_row(len(headers))
            merge_cells(current, cells)
        elif current:
            merge_cells(current, cells)

    if current:
        logical_rows.append(current)

    if not valid(headers, logical_rows):
        return fallback_projection_grid(chars)

    return [headers] + logical_rows
```

## 6. 参考 PDF 的期望行为

对于 `江苏银行-一生一世好游戏公司_1.pdf`，Mirror 表格应重建为：

| 页码 | 表头列数 | 逻辑数据行数 | 提取层 |
|------|----------|--------------|--------|
| 1 | 10 | 27 | `grid_reconstructor` |
| 2 | 10 | 31 | `grid_reconstructor` |
| 3 | 10 | 33 | `grid_reconstructor` |
| 4 | 0 | 0 | 无流水表 |

合成后的逻辑表应包含 91 条交易行，对应序号 1 到 91。

## 7. 实现映射

当前实现位置：

- `docmirror/core/extraction/table_kernel/char/grid_reconstructor.py`
  - 表头锚点检测
  - 列边线重建
  - 字符中心单元格分配
  - 逻辑行带恢复
  - 页脚过滤
- `docmirror/core/extraction/table_kernel/best_candidate.py`
  - 无框线流水候选的逻辑行质量评分
  - 防止碎片化物理行候选误胜
- `tests/unit/test_grid_reconstructor_logical_rows.py`
  - 合成多行流水回归测试
  - 候选选择回归测试

## 8. 设计不变量

Mirror 层必须先保留物理结构，再进入语义归一化：

- 不因为领域 schema 只有较少标准字段，就折叠物理列。
- 不把每条物理文本线都当作逻辑表格行。
- 不让原始行数主导无框线流水的候选选择。
- 当字符跨越已恢复分隔线时，不把整个词块粗暴分到单列。
- 不把页码等页面附属元素合并进最后一条交易记录。

## 9. 通用化策略

该算法不是江苏银行专用。它适用于具备以下特征的无框线表格：

- 存在重复出现的表头标签。
- 存在稳定的新记录起始锚点。
- 数据列具有可验证的类型一致性。
- 一条逻辑记录可能跨多条物理文本线。

迁移到新领域时，不应重写算法，而应替换领域配置：

| 领域 | 表头锚点 | 行起始锚点 | 数据类型锚点 |
|------|----------|------------|--------------|
| 银行流水 | 日期、摘要、余额、对方户名 | 序号、日期、时间 | 金额、余额、账号 |
| 支付账单 | 交易时间、交易类型、金额 | 交易时间、订单号 | 金额、交易对方、订单号 |
| 信用报告还款网格 | 月份、还款状态、金额 | 月份或期数 | 金额、状态、天数 |
| 通用清单 | 日期/时间/id 类表头 | 日期或行号 | 数字、日期、文本密度 |

通用规则是：

```text
表头锚点定义列边线；
记录起始锚点定义行边线；
数据类型一致性验证二者。
```
