import pytest
import time
from io import StringIO
import sys
from B.split_optimiser import solve, main as split_main


def run_split(input_str):
    """运行 split_optimiser main 函数并返回输出行列表。"""
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    sys.stdin = StringIO(input_str)
    captured_output = StringIO()
    sys.stdout = captured_output
    try:
        split_main()
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout
    return captured_output.getvalue().strip().splitlines()


# ============================================================
# test_single_warehouse: 单仓库刚好满足
# ============================================================
def test_single_warehouse():
    warehouses = [("A", 5, 10.0, 2.0)]
    result = solve(warehouses, 5)
    assert result is not None
    k, cost, alloc = result
    assert k == 1
    assert abs(cost - 20.0) < 1e-9  # 10 + 5*2 = 20
    assert alloc == [("A", 5)]


# ============================================================
# test_multi_warehouse_min_count: 多仓库时优先选最少仓库数
# ============================================================
def test_multi_warehouse_min_count():
    # 每个仓库库存5，Q=12，最少需要3个仓库（2个最多10，不够）
    warehouses = [
        ("A", 5, 10.0, 1.0),
        ("B", 5, 10.0, 1.0),
        ("C", 5, 10.0, 1.0),
    ]
    result = solve(warehouses, 12)
    assert result is not None
    k, cost, alloc = result
    assert k == 3  # 最少需要3个仓库
    assert sum(q for _, q in alloc) == 12
    # 成本：3个固定成本 + 12*单位成本 = 30 + 12 = 42
    assert abs(cost - 42.0) < 1e-9


# ============================================================
# test_minimize_cost: 相同仓库数时选成本最低
# ============================================================
def test_minimize_cost():
    # 两个仓库都能单独满足Q=5，选成本低的
    # X: 10 + 5*1 = 15
    # Y: 20 + 5*1 = 25
    warehouses = [
        ("X", 10, 10.0, 1.0),
        ("Y", 10, 20.0, 1.0),
    ]
    result = solve(warehouses, 5)
    assert result is not None
    k, cost, alloc = result
    assert k == 1
    assert abs(cost - 15.0) < 1e-9
    assert alloc == [("X", 5)]


# ============================================================
# test_lexicographic_tie: 成本相同时选字典序最小（PDF示例验证）
# ============================================================
def test_lexicographic_tie():
    # PDF示例：3 7 / AU 5 8 2 / CN 7 20 1 / US 4 3 4
    # 输出：1 27 / CN 7
    warehouses = [
        ("AU", 5, 8.0, 2.0),
        ("CN", 7, 20.0, 1.0),
        ("US", 4, 3.0, 4.0),
    ]
    result = solve(warehouses, 7)
    assert result is not None
    k, cost, alloc = result
    assert k == 1
    assert abs(cost - 27.0) < 1e-9  # 20 + 7*1 = 27
    assert alloc == [("CN", 7)]


# ============================================================
# test_impossible_order: 总库存不足，返回None
# ============================================================
def test_impossible_order():
    warehouses = [
        ("wh1", 20, 5.0, 1.0),
        ("wh2", 20, 5.0, 1.0),
    ]
    result = solve(warehouses, 50)
    assert result is None


# ============================================================
# test_zero_stock_warehouse: 有0库存仓库的情况
# ============================================================
def test_zero_stock_warehouse():
    # A库存为0，不能使用；B库存10，可以满足Q=5
    warehouses = [
        ("A", 0, 0.0, 0.1),
        ("B", 10, 10.0, 2.0),
    ]
    result = solve(warehouses, 5)
    assert result is not None
    k, cost, alloc = result
    assert k == 1
    # 0库存仓库不能被使用
    assert all(wid != "A" for wid, _ in alloc)
    assert alloc == [("B", 5)]
    assert abs(cost - 20.0) < 1e-9  # 10 + 5*2 = 20


# ============================================================
# test_equal_cost_ties: 相同成本的平局情况，验证字典序最小
# ============================================================
def test_equal_cost_ties():
    # 三个仓库 A, B, C
    # A: stock=5, fixed=10, unit=1
    # B: stock=5, fixed=5, unit=2
    # C: stock=5, fixed=3, unit=4
    # Q=6
    # k=1: 每个最多5件 < 6，都不行
    # k=2:
    #   A+B: A=5,B=1, 成本=10+5 + 5*1 + 1*2 = 22, 方案 [(A,5),(B,1)]
    #   A+C: A=5,C=1, 成本=10+3 + 5*1 + 1*4 = 22, 方案 [(A,5),(C,1)]
    #   B+C: C=5,B=1, 成本=5+3 + 5*4 + 1*2 = 30, 方案 [(B,1),(C,5)]
    # A+B 和 A+C 成本相同，选字典序更小的 A+B（因为 B < C）
    warehouses = [
        ("A", 5, 10.0, 1.0),
        ("B", 5, 5.0, 2.0),
        ("C", 5, 3.0, 4.0),
    ]
    result = solve(warehouses, 6)
    assert result is not None
    k, cost, alloc = result
    assert k == 2
    assert abs(cost - 22.0) < 1e-9
    # 字典序最小：A+B 而不是 A+C
    assert alloc == [("A", 5), ("B", 1)]


# ============================================================
# test_large_quantities: 大数据量（Q=2000, W=30）
# ============================================================
def test_large_quantities():
    # 构造30个仓库，每个库存2000，Q=2000
    # 每个仓库 fixed=100, unit=1，成本相同
    # 最少1个仓库，选id字典序最小的
    warehouses = []
    for i in range(30):
        wid = f"WH{i:02d}"
        warehouses.append((wid, 2000, 100.0, 1.0))

    start = time.time()
    result = solve(warehouses, 2000)
    elapsed = time.time() - start

    # 必须在合理时间内完成（暴力法需要10亿次枚举，绝对超时）
    assert elapsed < 5.0, f"DP算法太慢，耗时 {elapsed:.2f}s"

    assert result is not None
    k, cost, alloc = result
    assert k == 1
    assert abs(cost - 2100.0) < 1e-9  # 100 + 2000*1 = 2100
    # 字典序最小的id是 WH00
    assert alloc == [("WH00", 2000)]


# ============================================================
# test_same_cost_single_warehouse: 单仓库成本相同时选id小的
# ============================================================
def test_same_cost_single_warehouse():
    # A: 10 + 5*1 = 15
    # B: 7 + 5*1.6 = 15
    # 成本相同，选字典序更小的 A
    warehouses = [
        ("A", 5, 10.0, 1.0),
        ("B", 5, 7.0, 1.6),
    ]
    result = solve(warehouses, 5)
    assert result is not None
    k, cost, alloc = result
    assert k == 1
    assert abs(cost - 15.0) < 1e-9
    assert alloc == [("A", 5)]


# ============================================================
# test_lexicographic_smaller_qty: 同仓库集合时，小id分配量更小更优
# ============================================================
def test_lexicographic_smaller_qty():
    # 两个仓库 A 和 B，Q=6
    # A: stock=5, fixed=10, unit=2
    # B: stock=5, fixed=10, unit=2
    # 单位成本相同，所以无论怎么分配，总成本都一样 = 10+10 + 6*2 = 32
    # 分配方式1: A=1, B=5 → [(A,1), (B,5)]
    # 分配方式2: A=5, B=1 → [(A,5), (B,1)]
    # 字典序：[(A,1), (B,5)] < [(A,5), (B,1)]（A的数量1 < 5）
    warehouses = [
        ("A", 5, 10.0, 2.0),
        ("B", 5, 10.0, 2.0),
    ]
    result = solve(warehouses, 6)
    assert result is not None
    k, cost, alloc = result
    assert k == 2
    assert abs(cost - 32.0) < 1e-9
    # 字典序最小：A的分配量尽可能小
    assert alloc == [("A", 1), ("B", 5)]


# ============================================================
# test_main_output: 验证 main 函数的输出格式（整数成本）
# ============================================================
def test_main_output_integer():
    # 整数成本输出不带小数
    input_data = "1 5\nA 5 10.0 2.0"
    res = run_split(input_data)
    assert res[0] == "1 20"  # 成本 10 + 5*2 = 20，整数
    assert res[1] == "A 5"


# ============================================================
# test_main_output_impossible: 验证 main 函数不可满足时输出 -1
# ============================================================
def test_main_output_impossible():
    input_data = "2 50\nwh1 20 5.0 1.0\nwh2 20 5.0 1.0"
    res = run_split(input_data)
    assert res[0] == "-1"


# ============================================================
# test_pdf_example_solve: 验证PDF示例（通过solve函数）
# ============================================================
def test_pdf_example_solve():
    # PDF官方示例验证
    warehouses = [
        ("AU", 5, 8.0, 2.0),
        ("CN", 7, 20.0, 1.0),
        ("US", 4, 3.0, 4.0),
    ]
    result = solve(warehouses, 7)
    assert result is not None
    k, cost, alloc = result
    assert k == 1
    assert abs(cost - 27.0) < 1e-9
    assert alloc == [("CN", 7)]
