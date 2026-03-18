# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

from docmirror.core.table.table_structure_fix import merge_split_rows
import json

def test_semantic_closure():
    # Simulate a CCB-style cross-page split table with a long memo
    table = [
        ["记账日期", "记账时间", "币种", "钞/汇", "资金流向", "交易金额", "账户余额", "交易网点", "对方户名", "对方账号", "摘要"],
        ["2024-05-15", "10:30:15", "人民币", "钞", "支出", "1,500.00", "4,500.00", "建行北京分行", "张三", "6227001234567890", "货款"],
        ["", "", "", "", "", "", "", "这是跨页被折断的一", "", "", ""], # First part of broken memo in Col 7
        ["段非常长的报销附言", "", "", "", "", "", "", "并且内容含有数字234", "", "", "可能跨越多行"], # Second part
        ["2024-05-16", "09:00:00", "人民币", "钞", "存入", "2,000.00", "6,500.00", "建行上海分行", "李四", "6227000987654321", "工资"]
    ]
    
    print("--- RAW TABLE ---")
    for r in table: print(r)
    
    merged = merge_split_rows(table)
    
    print("\n--- MERGED TABLE ---")
    for r in list(merged): print(r)
    
    assert len(merged) == 3, f"Expected 3 logical rows (header + 2 records), got {len(merged)}"
    
    # Check if the split rows merged into the first transaction
    first_record = merged[1]
    
    # Asserting length
    assert "2024-05-15" in first_record[0]
    
    # Print the specific column where we expect the memo to be merged
    print("\nMerged Column 7:")
    print(repr(first_record[7]))
    print("\nMerged Column 10:")
    print(repr(first_record[10]))
    print("\nMerged Column 0:")
    print(repr(first_record[0]))
    
    print("\n✅ Semantic Closure Unity Test PASSED!")
    
if __name__ == "__main__":
    test_semantic_closure()