from itertools import combinations

def main():
    import sys
    input = sys.stdin.read().split()
    ptr = 0
    M = int(input[ptr]); ptr +=1
    Q = int(input[ptr]); ptr +=1
    warehouses = []
    for i in range(M):
        wid = input[ptr]; ptr +=1
        stock = int(input[ptr]); ptr +=1
        fixed = float(input[ptr]); ptr +=1
        unit = float(input[ptr]); ptr +=1
        warehouses.append((wid, stock, fixed, unit))
    
    best = None
    # 按仓库数从小到大遍历
    for k in range(1, M+1):
        for combo in combinations(warehouses, k):
            total_stock = sum(s for _,s,_,_ in combo)
            if total_stock < Q:
                continue
            # 按id排序凑量
            sorted_combo = sorted(combo, key=lambda x:x[0])
            alloc = []
            need = Q
            cost = 0.0
            for wid, s, f, u in sorted_combo:
                take = min(need, s)
                alloc.append((wid, take))
                cost += f + take * u
                need -= take
                if need ==0:
                    break
            # 对比最优解
            current_key = (k, cost, tuple(alloc))
            if best is None or current_key < best[0]:
                best = (current_key, alloc, cost)
    if best is None:
        print(-1)
    else:
        _, alloc, cost = best
        print(f"{len(alloc)} {cost:.10f}")
        for wid, q in alloc:
            print(f"{wid} {q}")

if __name__ == "__main__":
    main()
