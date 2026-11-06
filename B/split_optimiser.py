from collections import deque

INF = float('inf')
EPS = 1e-9


def solve(warehouses, Q):
    """
    使用DP算法求解仓库分配优化问题。

    参数:
        warehouses: list of (warehouse_id, stock, fixed_cost, unit_cost)
        Q: 需要分配的总数量

    返回:
        (k_min, min_cost, allocation) 或 None（不可满足）
        allocation: list of (warehouse_id, allocated_qty)，按id排序
    """
    W = len(warehouses)
    if W == 0 or Q == 0:
        return None

    # 按 warehouse_id 字典序排序
    warehouses.sort(key=lambda x: x[0])

    # suffix_dp[i][k][q] = 使用第 i..W-1 个仓库，恰好选 k 个，凑恰好 q 件的最小成本
    # 用 (W+1) x (W+1) x (Q+1) 的三维数组
    suffix_dp = [[[INF] * (Q + 1) for _ in range(W + 1)] for _ in range(W + 1)]
    suffix_dp[W][0][0] = 0.0

    # 从后往前DP，单调队列优化
    for i in range(W - 1, -1, -1):
        wid, stock, fixed, unit = warehouses[i]
        s = min(stock, Q)  # 最多拿 min(stock, Q) 件

        # 复制不选当前仓库的情况
        for k in range(W + 1):
            for q in range(Q + 1):
                suffix_dp[i][k][q] = suffix_dp[i + 1][k][q]

        # 选当前仓库的情况，对每个 k 做单调队列优化
        for k in range(1, W + 1):
            # g[q'] = suffix_dp[i+1][k-1][q'] - q' * unit
            # 我们要对每个 q 求 min_{q' = q-s .. q-1} g[q']
            dq = deque()  # 存储 q' 的索引，保证 g[q'] 单调递增

            for q in range(1, Q + 1):
                # 将 q-1 加入队列（窗口右边界扩展）
                q_prime = q - 1
                if q_prime <= Q:
                    g_val = suffix_dp[i + 1][k - 1][q_prime] - q_prime * unit
                    while dq and (suffix_dp[i + 1][k - 1][dq[-1]] - dq[-1] * unit) >= g_val - EPS:
                        dq.pop()
                    dq.append(q_prime)

                # 移除窗口左边 < q - s 的元素
                left_bound = q - s
                while dq and dq[0] < left_bound:
                    dq.popleft()

                # 队首是最小值
                if dq:
                    best_q_prime = dq[0]
                    candidate = suffix_dp[i + 1][k - 1][best_q_prime] + fixed + (q - best_q_prime) * unit
                    if candidate < suffix_dp[i][k][q] - EPS:
                        suffix_dp[i][k][q] = candidate

    # 找最小的 k_min 和对应的 min_cost
    k_min = None
    min_cost = INF
    for k in range(1, W + 1):
        cost = suffix_dp[0][k][Q]
        if cost < INF - EPS:
            k_min = k
            min_cost = cost
            break  # k 从小到大，第一个找到的就是最少仓库数

    if k_min is None:
        return None

    # 构造字典序最小的分配方案
    # 按 id 从小到大决策，能用当前仓库就用（保证字典序最小），且分配量尽可能小
    allocation = []
    k_remain = k_min
    q_remain = Q
    cost_remain = min_cost

    for i in range(W):
        wid, stock, fixed, unit = warehouses[i]
        if k_remain <= 0 or q_remain <= 0:
            break

        max_take = min(stock, q_remain)
        if max_take < 1:
            continue

        # 尝试 t 从 1 到 max_take，找最小的可行 t
        found = False
        for t in range(1, max_take + 1):
            if k_remain - 1 < 0 or q_remain - t < 0:
                continue
            rest_cost = suffix_dp[i + 1][k_remain - 1][q_remain - t]
            if rest_cost < INF - EPS:
                total = fixed + t * unit + rest_cost
                if abs(total - cost_remain) < EPS:
                    # 选择这个 t（最小的可行 t）
                    allocation.append((wid, t))
                    k_remain -= 1
                    q_remain -= t
                    cost_remain -= (fixed + t * unit)
                    found = True
                    break

        # 如果没找到，说明不使用这个仓库

    return (k_min, min_cost, allocation)


def format_cost(cost):
    """格式化成本：整数就输出整数，否则输出最简形式。"""
    if abs(cost - int(cost)) < EPS:
        return str(int(cost))
    # 去掉末尾多余的0和可能的小数点
    s = f"{cost:.10f}".rstrip('0').rstrip('.')
    return s


def main():
    import sys
    input_data = sys.stdin.read().split()
    ptr = 0
    M = int(input_data[ptr]); ptr += 1
    Q = int(input_data[ptr]); ptr += 1
    warehouses = []
    for i in range(M):
        wid = input_data[ptr]; ptr += 1
        stock = int(input_data[ptr]); ptr += 1
        fixed = float(input_data[ptr]); ptr += 1
        unit = float(input_data[ptr]); ptr += 1
        warehouses.append((wid, stock, fixed, unit))

    result = solve(warehouses, Q)
    if result is None:
        print(-1)
    else:
        k_min, min_cost, allocation = result
        # allocation 已经按 id 排序（因为我们按排序后的顺序构造）
        print(f"{k_min} {format_cost(min_cost)}")
        for wid, qty in allocation:
            print(f"{wid} {qty}")


if __name__ == "__main__":
    main()
