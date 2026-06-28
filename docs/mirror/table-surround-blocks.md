# 表格环绕区识别

**日期：** 2026-06-25  
**范围：** Mirror 层中表格 bbox 之外的表前头部、表后摘要、声明、签章、页脚识别  
**参考样例：** 交通银行宁夏回族自治区分行明细对账单，表格后存在当前账单/本月累计汇总区

## 1. 问题定义

明细表重建只能覆盖表格内部。很多银行流水、对账单、回单类 PDF 在表格之前和表格之后还有重要信息：

- 表前头部：标题、开户机构、币种、年份、月份、页码、账号、户名、印章。
- 表后摘要：本页或当前账单借贷笔数、累计借贷笔数、累计借贷发生额、出单截至日期。
- 表后声明：`以下此页无其他交易信息`、免责声明、打印说明。
- 视觉证据：红章、二维码、水印、签名、页码。

这些内容不能被合并进明细表，也不能丢弃。Mirror 层应把它们作为表格环绕区块保存，并尽可能结构化。

## 2. 第一性原理

一个页面不是只有表格，而是多个空间区域的组合：

```text
page
  ├── table_preamble      表前头部
  ├── table_body          明细表
  ├── table_postamble     表后摘要/声明
  ├── side_artifacts      印章、二维码、边注
  └── page_footer         页码、打印时间等页面附属信息
```

表格算法恢复的是 `table_body`。表格 bbox 之外的 token 应进入“残余区域识别”流程：

```text
residual_tokens = all_page_tokens - tokens_inside_table_bbox
```

然后根据相对位置、文本模式、视觉形态和与表格的关系，把 residual tokens 分类为结构块。

核心原则：

- 表格 bbox 结束不等于页面内容结束。
- 表格之外的内容仍属于 Mirror 的物理事实。
- 表后摘要通常是对表格内容的校验信号，而不是普通段落。
- 印章、二维码、签名这类视觉对象即使没有可解析文本，也应作为证据块保存。

## 3. 区域切分

### 3.1 表格 bbox

对于有框线表格，表格 bbox 可由外框线或最外层单元格边界得到：

```text
table_bbox = [x0, y0, x1, y1]
```

对于无框线表格，bbox 由以下信息估计：

- 表头 top。
- 首列/末列分隔线。
- 第一条和最后一条逻辑行带。
- 最后一条非页脚物理文本线 bottom。

### 3.2 表前区

表前区是：

```text
preamble_bbox = [0, 0, page_width, table_bbox.top)
```

常见类型：

- `document_title`
- `statement_period`
- `account_identity`
- `institution_identity`
- `page_index`
- `seal_or_stamp`

### 3.3 表后区

表后区是：

```text
postamble_bbox = [0, table_bbox.bottom, page_width, page_height]
```

但不是所有表后 token 都是同一类。需要再切成水平 band：

```text
postamble_bands = group_by_y_gap(tokens_below_table)
```

每个 band 再按语义分类：

- `ledger_page_summary`
- `ledger_period_summary`
- `statement_cutoff`
- `no_more_transactions_notice`
- `page_footer`
- `next_table_preamble`
- `unknown_residual`

## 4. 表后摘要识别

表后摘要一般由键值对组成，常见模式：

```text
当前账单借方发生数：9
当前账单贷方发生数：2
本月累计借方发生数：9
本月累计贷方发生数：2
本月累计借方发生额：125,520.71
本月累计贷方发生额：120,003.75
出单截至日期：2025-09-30
```

识别步骤：

1. 从表格 bbox 下方收集 tokens。
2. 按 y 坐标聚合为文本行。
3. 在每行中识别 `label: value`、`label：value`、相邻 label/value token。
4. 对金额、日期、整数分别做类型归一化。
5. 将同一视觉 band 内的键值对聚合成一个 `ledger_summary` 块。

推荐输出：

```json
{
  "block_type": "key_value",
  "content_role": "table_postamble.ledger_summary",
  "bbox": [20, 383, 598, 433],
  "fields": {
    "current_debit_count": "9",
    "current_credit_count": "2",
    "period_debit_count": "9",
    "period_credit_count": "2",
    "period_debit_amount": "125,520.71",
    "period_credit_amount": "120,003.75",
    "statement_cutoff_date": "2025-09-30"
  }
}
```

## 5. 表后声明识别

声明通常是横向居中或跨宽度文本，例如：

```text
--------------------------------------以下此页无其他交易信息--------------------------------------
```

识别策略：

- 去掉重复横线、短横线、装饰符。
- 保留核心文本：`以下此页无其他交易信息`。
- 分类为 `table_postamble.notice`。

推荐输出：

```json
{
  "block_type": "text",
  "content_role": "table_postamble.notice",
  "text": "以下此页无其他交易信息",
  "bbox": [176, 435, 666, 446]
}
```

这个块可以作为终止信号：当前页面后续没有更多交易行。

## 6. 表前头部识别

表前头部和表后摘要本质上是同一个“表格环绕区”问题，只是位置不同。

以交通银行样例为例，表前区包含：

```text
交通银行宁夏回族自治区分行明细对账单
开户机构：交通银行银川开发区支行
币种：人民币
年份：2025
月份：09
页码：本月第1份-第1页
账号：641301106013000859983
户名：重庆正大华日软件有限公司银川分公司
交通银行 对账专用章 DAEF3FD8
```

推荐分类：

| 内容 | content_role | 结构化字段 |
|------|--------------|------------|
| 对账单标题 | `document_header.title` | `title` |
| 开户机构 | `document_header.institution` | `opening_branch` |
| 币种/年份/月 | `document_header.statement_context` | `currency`, `year`, `month` |
| 页码 | `document_header.pagination` | `page_index` |
| 账号/户名 | `document_header.account_identity` | `account_number`, `account_name` |
| 红章 | `document_header.seal` | `seal_text`, `seal_code`, `seal_bbox` |

## 7. 校验关系

表格环绕区不是纯展示信息，它还能反向校验明细表：

- `current_debit_count + current_credit_count` 应等于当前表格内交易行数。
- `period_debit_amount` 应等于本月或本文档范围内借方金额合计。
- `period_credit_amount` 应等于本月或本文档范围内贷方金额合计。
- `statement_cutoff_date` 应大于等于所有交易日期。
- `no_more_transactions_notice` 表示本页明细表已结束。

如果校验不一致，不应静默修正表格，而应记录质量事件：

```text
surround_summary_mismatch
ledger_count_mismatch
ledger_amount_mismatch
```

## 8. 多页策略

多页流水中，每页都可能有自己的表前/表后区：

- 第一页通常有完整文档头。
- 中间页可能只有页码、账号、续页头。
- 末页通常有累计汇总、声明、盖章。

Mirror 应同时保留：

- `page_surround_blocks`：每页物理环绕区块。
- `document_summary`：跨页聚合后的结构化摘要。

当同一字段在多页重复出现时：

- 完全一致：合并为一个 document-level 字段，并保留 page refs。
- 不一致：保留所有候选，并标记冲突。

## 9. 与明细表重建的关系

推荐的整体流程：

```text
page tokens
  ↓
detect table candidates
  ↓
reconstruct table body
  ↓
derive table bbox and occupied token set
  ↓
extract residual tokens outside table bbox
  ↓
classify residual bands:
    - preamble
    - postamble
    - seal
    - notice
    - footer
  ↓
cross-check residual summaries against table body
  ↓
emit mirror blocks + quality observations
```

表格 body 算法和环绕区算法应该共享同一个空间索引，避免同一个 token 被重复归属。

## 10. 设计不变量

- 表格最后一条交易行的 bottom 不是页面内容结束。
- 表后摘要不能作为交易行进入明细表。
- 表后声明不能作为普通噪声丢弃。
- 表前头部和表后摘要都应带 bbox 和 source span。
- 如果摘要字段可以校验表格，应进入质量层，而不是只进入展示层。
- 无法分类的残余 token 也应进入 `unknown_residual`，除非明确是水印或装饰噪声。

## 11. 当前样例的期望输出

对于 `银行流水_股份有限公司重庆分行_20250930_1.pdf`：

| 区域 | y 范围约略 | 期望角色 |
|------|------------|----------|
| 页面顶部到 y=117 | 表前头部 | 标题、开户机构、币种、年份、月份、页码、账号、户名、红章 |
| y=117 到 y=380 | 明细表 | 11 条交易行 |
| y=383 到 y=433 | 表后摘要 | 当前账单和本月累计借贷笔数/金额、出单截至日期 |
| y=435 附近 | 表后声明 | 以下此页无其他交易信息 |

这说明 Mirror 层需要一个独立的“表格环绕区识别算法”，与明细表网格重建并列，而不是把它们混在同一个表格解析函数中。
