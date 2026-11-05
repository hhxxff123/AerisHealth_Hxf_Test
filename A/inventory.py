def main():
    import sys
    input_lines = [line.strip() for line in sys.stdin if line.strip()]
    ptr = 0
    S, N = map(int, input_lines[ptr].split())
    ptr += 1
    on_hand = S
    reserved = dict()
    processed_events = set()

    for _ in range(N):
        parts = input_lines[ptr].split() if ptr < len(input_lines) else []
        ptr += 1
        op = parts[0] if len(parts) >= 1 else ""
        event_id = parts[1] if len(parts) >= 2 else ""

        if event_id in processed_events:
            total_reserved = sum(reserved.values())
            print(f"DUPLICATE {on_hand} {total_reserved}")
            continue

        valid = True
        if op not in ("RESERVE", "RELEASE", "SHIP", "RESTOCK"):
            valid = False
        elif op in ("RESERVE", "RELEASE", "SHIP") and len(parts) != 4:
            valid = False
        elif op == "RESTOCK" and len(parts) != 3:
            valid = False

        if not valid:
            processed_events.add(event_id)
            total_reserved = sum(reserved.values())
            print(f"REJECTED {on_hand} {total_reserved}")
            continue

        try:
            qty = int(parts[-1])
            if qty <= 0:
                raise ValueError
        except:
            processed_events.add(event_id)
            total_reserved = sum(reserved.values())
            print(f"REJECTED {on_hand} {total_reserved}")
            continue

        order_id = parts[2] if op in ("RESERVE", "RELEASE", "SHIP") else ""
        success = True

        if op == "RESERVE":
            available = on_hand - sum(reserved.values())
            if available < qty:
                success = False
            else:
                reserved[order_id] = reserved.get(order_id, 0) + qty
        elif op == "RELEASE":
            if reserved.get(order_id, 0) < qty:
                success = False
            else:
                reserved[order_id] -= qty
                if reserved[order_id] == 0:
                    del reserved[order_id]
        elif op == "SHIP":
            if reserved.get(order_id, 0) < qty:
                success = False
            else:
                reserved[order_id] -= qty
                if reserved[order_id] == 0:
                    del reserved[order_id]
                on_hand -= qty
        elif op == "RESTOCK":
            on_hand += qty

        processed_events.add(event_id)
        total_reserved = sum(reserved.values())
        if success:
            print(f"OK {on_hand} {total_reserved}")
        else:
            print(f"REJECTED {on_hand} {total_reserved}")

    for oid in sorted(reserved.keys()):
        print(f"OPEN {oid} {reserved[oid]}")

if __name__ == "__main__":
    main()
