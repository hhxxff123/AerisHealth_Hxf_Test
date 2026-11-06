# AerisHealth Full Stack Coding Assessment

This repository contains the complete submission for the AerisHealth Full Stack Coding Assessment. It includes four tasks (A, B, C, and a full-stack application) designed to evaluate algorithmic problem-solving, system design, and full-stack development capabilities.

**Total Assessment: 100 points**

---

## Repository Structure

```
/
├── A/          # Task A: Inventory Reservation Ledger
├── B/          # Task B: Fulfilment Split Optimiser
├── C/          # Task C: Xero Integration Review
└── app/        # Task D: Full-Stack Variant PDP
    ├── backend/   # FastAPI backend (Python)
    └── frontend/  # React + TypeScript + Vite frontend
```

---

## Prerequisites

- **Python 3.10+** (3.11+ recommended for the backend)
- **Node.js 18+**
- **npm** or **yarn**

---

## Task A - Inventory Reservation Ledger

### Overview

An event-driven inventory ledger system that processes a stream of operations (RESERVE, RELEASE, SHIP, RESTOCK) and maintains accurate stock and reservation counts per SKU. The system outputs the final state of available, reserved, and shipped quantities for each SKU.

### How to Run

```bash
python A/inventory.py < input.txt
```

### How to Run Tests

```bash
python -m pytest A/test_inventory.py -v
```

### Complexity Analysis

See [A/COMPLEXITY.md](A/COMPLEXITY.md) for detailed time and space complexity analysis.

### Algorithm

- **Time Complexity:** O(N) where N is the number of events
- **Data Structures:** Hash map (dict) for SKU state tracking + set for reservation ID lookups
- **Approach:** Single-pass linear scan with constant-time operations per event

---

## Task B - Fulfilment Split Optimiser

### Overview

A warehouse allocation optimiser that determines the minimum-cost way to fulfil an order from multiple warehouses. The solution prioritises minimising the number of warehouses used, and then minimising the total cost as a secondary objective.

### How to Run

```bash
python B/split_optimiser.py < input.txt
```

### How to Run Tests

```bash
python -m pytest B/test_split_optimiser.py -v
```

### Complexity Analysis

See [B/COMPLEXITY.md](B/COMPLEXITY.md) for detailed time and space complexity analysis.

### Algorithm

- **Time Complexity:** O(W^2 x Q) where W is the number of warehouses and Q is the quantity
- **Approach:** Monotonic queue-optimised dynamic programming with lexicographic tie-breaking for warehouse count priority

---

## Task C - Xero Integration Review

### Overview

Six written questions covering Xero API integration design and troubleshooting. The answers demonstrate understanding of OAuth flows, error diagnosis, incremental sync strategies, rate limiting, data integrity, and observability.

### Files

- [C/answers.md](C/answers.md) - Complete answers to all six questions

### Topics Covered

1. OAuth 2.0 authentication flow and token management
2. Error diagnosis for sync failures
3. Incremental sync strategies and delta tracking
4. Rate limiting handling and retry policies
5. Data integrity and reconciliation patterns
6. Observability, logging, and monitoring

---

## Full-Stack App - Variant PDP

A full-stack Product Detail Page (PDP) application featuring multi-dimensional variant selection, real-time SKU resolution, and a shopping cart with concurrency safety.

### Backend (FastAPI)

#### Tech Stack

- Python 3.11+
- FastAPI
- SQLite (with WAL mode for improved concurrency)
- Pydantic for validation

#### How to Run

```bash
cd app/backend
pip install fastapi uvicorn
python main.py
```

Or with uvicorn directly:

```bash
cd app/backend
pip install fastapi uvicorn
python main.py
```

The server will be available at `http://localhost:8001`.

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/products/{id}` | Get product with all variants and SKUs |
| `POST` | `/api/cart/items` | Add item to cart (requires `Idempotency-Key` header) |
| `GET` | `/api/cart` | Get cart with line items and order totals |

#### How to Run Tests

```bash
python -m pytest app/backend/test_main.py -v
```

#### Key Features

- **Optimistic Locking:** `UPDATE ... WHERE stock >= qty` pattern prevents overselling under concurrent load
- **Idempotency:** Server-side caching via `Idempotency-Key` header ensures duplicate requests do not double-add items
- **Structured Error Responses:** Unified `{ error: { code, message } }` format
- **Server-Side Validation:** Prices and stock are always read from the database - client values are never trusted
- **WAL Mode:** SQLite Write-Ahead Logging for improved concurrent read performance

---

### Frontend (React + Vite)

#### Tech Stack

- React 19
- TypeScript (strict mode)
- Vite
- Vitest + React Testing Library
- Axios

#### How to Install Dependencies

```bash
cd app/frontend
npm install
```

#### Development Mode

```bash
npm run dev
```

The development server runs on `http://localhost:3000` and proxies API requests to `http://localhost:8001`.

#### Build for Production

```bash
npm run build
```

#### How to Run Tests

```bash
npm run test
```

#### Features

- **Dual-Dimension Variant Selector:** Color + size matrix selection with visual feedback
- **Real-Time SKU Resolution:** Instant updates of price, image, and stock status as options change
- **Quantity Selector:** With stock-bound validation (cannot exceed available stock)
- **Add-to-Cart:** Loading states and idempotency key management
- **Accessible Feedback:** Clear error and success messages with proper ARIA attributes
- **Responsive Layout:** Optimised for both mobile and desktop viewports

---

## Architecture Notes

### Backend Architecture

- **Layered Design:** Clear separation between route handlers, business logic, and data access
- **Database:** SQLite with WAL mode and optimistic locking for concurrent safety
- **Validation:** Pydantic models ensure type safety at API boundaries

### Frontend Architecture

- **Component-Based Design:** Modular, reusable React components
- **API Layer:** Centralised API client with axios for consistent request handling
- **Type Safety:** Full TypeScript coverage with strict mode enabled

### Concurrency Safety

The backend uses an optimistic locking pattern (`UPDATE ... WHERE stock >= qty`) within a transaction to prevent overselling. If the update affects zero rows, the request fails with a stock insufficiency error.

### Idempotency

The `POST /api/cart/items` endpoint requires an `Idempotency-Key` header. The server caches responses for each key, so retried requests with the same key return the cached result without modifying the cart again.

---

## Assumptions

- **Task A:** Input is complete and read all at once before processing. Events are well-formed per the specification.
- **Task B:** Costs may be floating-point numbers. Output formatting strips unnecessary trailing zeros.
- **Task C:** Assumes Xero API v3 and the official `xero-python` SDK.
- **App - Backend:** Single-user cart for simplicity. A production implementation would require user authentication and per-user carts.
- **App - Frontend:** Product images use placeholder URLs. In production, these would be served from a CDN or image hosting service.
- **Testing:** All tests assume the specified Python and Node.js versions are available in the environment.

---

## Known Limitations

- **No User Authentication:** The shopping cart is single-user (global). Production would require user auth and per-user carts.
- **SQLite Concurrency:** While WAL mode helps, SQLite has limitations under high write concurrency. This is sufficient for an interview project but a production deployment would use PostgreSQL or MySQL.
- **No Client-Side Routing:** The frontend is a single page with no router. A larger app would benefit from React Router.
- **No Cart Persistence Across Sessions:** The cart is stored only in the database without user session binding.
- **No Product List Page:** Only a single PDP is implemented; there is no product listing or search.

---

## AI Usage Disclosure

AI tools (Trae Work) were used to assist with the following aspects of this project:

- Initial code scaffolding and boilerplate generation
- Algorithm implementation verification and edge-case review
- Test case generation for boundary conditions
- Documentation drafting and formatting

All core logic, architecture decisions, and final code reviews were performed manually. All test results were verified to pass before submission.

---

## Running All Tests

### Python Tests

```bash
# Task A
python -m pytest A/test_inventory.py -v

# Task B
python -m pytest B/test_split_optimiser.py -v

# Backend (Task D)
python -m pytest app/backend/test_main.py -v
```

### Frontend Tests

```bash
cd app/frontend
npm test
```
