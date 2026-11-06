import pytest
from io import StringIO
import sys
from A.inventory import main as inventory_main


def run_inventory(input_str):
    """运行库存管理系统，返回输出行列表"""
    sys.stdin = StringIO(input_str)
    captured_output = StringIO()
    sys.stdout = captured_output
    inventory_main()
    sys.stdin = sys.__stdin__
    sys.stdout = sys.__stdout__
    return captured_output.getvalue().strip().splitlines()


# 1. 正常预留成功
def test_normal_reserve_success():
    input_data = "100 1\nRESERVE e1 o100 20"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"


# 2. 重复事件ID返回DUPLICATE且不改变状态
def test_duplicate_event_id():
    input_data = "100 2\nRESERVE e1 o100 20\nRESERVE e1 o100 20"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"
    assert result_lines[1] == "DUPLICATE 100 20"


# 3. 超出可用库存被拒绝
def test_over_stock_reject():
    input_data = "100 1\nRESERVE e1 o100 120"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"


# 4. 正常释放预留
def test_release_success():
    input_data = "100 2\nRESERVE e1 o100 20\nRELEASE e2 o100 10"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"
    assert result_lines[1] == "OK 100 10"


# 5. 释放超过预留数量被拒绝
def test_release_exceed_reject():
    input_data = "100 2\nRESERVE e1 o100 20\nRELEASE e2 o100 30"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"
    assert result_lines[1] == "REJECTED 100 20"


# 6. 正常发货（同时减少on_hand和reserved）
def test_ship_success():
    input_data = "100 2\nRESERVE e1 o100 20\nSHIP e2 o100 15"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"
    assert result_lines[1] == "OK 85 5"


# 7. 发货超过预留被拒绝
def test_ship_exceed_reject():
    input_data = "100 2\nRESERVE e1 o100 20\nSHIP e2 o100 25"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"
    assert result_lines[1] == "REJECTED 100 20"


# 8. 补货成功
def test_restock_success():
    input_data = "100 1\nRESTOCK e1 50"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 150 0"


# 9. 无效操作类型被拒绝
def test_invalid_op_reject():
    input_data = "100 1\nINVALID e1 o100 10"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"


# 10. 负数量被拒绝
def test_negative_qty_reject():
    input_data = "100 1\nRESERVE e1 o100 -5"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"


# 11. 零数量被拒绝
def test_zero_qty_reject():
    input_data = "100 1\nRESERVE e1 o100 0"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"


# 12. 格式错误被拒绝
def test_malformed_input_reject():
    input_data = "100 2\nRESERVE e1 o100\nRESERVE e2"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"
    assert result_lines[1] == "REJECTED 100 0"


# 13. 最后输出OPEN预留，按order_id排序
def test_open_reservations():
    input_data = "100 3\nRESERVE e1 o200 10\nRESERVE e2 o100 20\nRESERVE e3 o300 5"
    result_lines = run_inventory(input_data)
    # 前3行是命令结果，后面是OPEN列表
    assert result_lines[3] == "OPEN o100 20"
    assert result_lines[4] == "OPEN o200 10"
    assert result_lines[5] == "OPEN o300 5"


# 14. 被拒绝的操作也算processed，重复返回DUPLICATE
def test_rejected_is_idempotent():
    input_data = "100 2\nRESERVE e1 o100 200\nRESERVE e1 o100 10"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"
    assert result_lines[1] == "DUPLICATE 100 0"


# 15. 大数字测试（10^12级别）
def test_large_numbers():
    big = 10**12
    input_data = f"{big} 3\nRESERVE e1 o100 {big//2}\nSHIP e2 o100 {big//4}\nRESTOCK e3 {big}"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == f"OK {big} {big//2}"
    assert result_lines[1] == f"OK {big - big//4} {big//2 - big//4}"
    assert result_lines[2] == f"OK {big - big//4 + big} {big//2 - big//4}"


# 16. 同一event_id不同操作也返回DUPLICATE
def test_idempotency_across_operations():
    input_data = "100 2\nRESERVE e1 o100 20\nRELEASE e1 o100 10"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 100 20"
    assert result_lines[1] == "DUPLICATE 100 20"


# PDF示例验证
def test_pdf_example():
    input_data = (
        "10 6\n"
        "RESERVE e1 o100 4\n"
        "RESERVE e2 o200 7\n"
        "SHIP e3 o100 2\n"
        "RELEASE e4 o100 2\n"
        "RESTOCK e5 3\n"
        "RESERVE e2 o999 1"
    )
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 10 4"
    assert result_lines[1] == "REJECTED 10 4"
    assert result_lines[2] == "OK 8 2"
    assert result_lines[3] == "OK 8 0"
    assert result_lines[4] == "OK 11 0"
    assert result_lines[5] == "DUPLICATE 11 0"
