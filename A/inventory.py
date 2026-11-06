def main():
    import sys
    input_lines = [line.strip() for line in sys.stdin if line.strip()]
    ptr = 0
    S, N = map(int, input_lines[ptr].split())
    ptr += 1

    # 现有库存总量
    on_hand = S
    # 各订单的预留数量映射: order_id -> reserved_qty
    reserved = dict()
    # 所有预留总量的缓存，避免每次 O(U) 重新计算，O(1) 访问
    total_reserved = 0
    # 已处理事件集合，用于幂等性保证
    processed_events = set()

    for _ in range(N):
        parts = input_lines[ptr].split() if ptr < len(input_lines) else []
        ptr += 1
        op = parts[0] if len(parts) >= 1 else ""
        event_id = parts[1] if len(parts) >= 2 else ""

        # 幂等性检查：已处理过的事件直接返回 DUPLICATE
        if event_id in processed_events:
            print(f"DUPLICATE {on_hand} {total_reserved}")
            continue

        # 校验操作类型和参数数量
        valid = True
        if op not in ("RESERVE", "RELEASE", "SHIP", "RESTOCK"):
            valid = False
        elif op in ("RESERVE", "RELEASE", "SHIP") and len(parts) != 4:
            valid = False
        elif op == "RESTOCK" and len(parts) != 3:
            valid = False

        if not valid:
            processed_events.add(event_id)
            print(f"REJECTED {on_hand} {total_reserved}")
            continue

        # 校验数量：必须为正整数
        try:
            qty = int(parts[-1])
            if qty <= 0:
                raise ValueError
        except:
            processed_events.add(event_id)
            print(f"REJECTED {on_hand} {total_reserved}")
            continue

        order_id = parts[2] if op in ("RESERVE", "RELEASE", "SHIP") else ""
        success = True

        if op == "RESERVE":
            # 可用库存 = 现有库存 - 已预留总量
            available = on_hand - total_reserved
            if available < qty:
                success = False
            else:
                reserved[order_id] = reserved.get(order_id, 0) + qty
                total_reserved += qty
        elif op == "RELEASE":
            # 释放预留，不能超过该订单已预留数量
            if reserved.get(order_id, 0) < qty:
                success = False
            else:
                reserved[order_id] -= qty
                total_reserved -= qty
                if reserved[order_id] == 0:
                    del reserved[order_id]
        elif op == "SHIP":
            # 发货：同时减少预留和现有库存
            if reserved.get(order_id, 0) < qty:
                success = False
            else:
                reserved[order_id] -= qty
                total_reserved -= qty
                if reserved[order_id] == 0:
                    del reserved[order_id]
                on_hand -= qty
        elif op == "RESTOCK":
            # 补货：增加现有库存
            on_hand += qty

        processed_events.add(event_id)
        if success:
            print(f"OK {on_hand} {total_reserved}")
        else:
            print(f"REJECTED {on_hand} {total_reserved}")

    # 输出所有未关闭的预留，按 order_id 排序
    for oid in sorted(reserved.keys()):
        print(f"OPEN {oid} {reserved[oid]}")


if __name__ == "__main__":
    main()
