"""
AerisHealth 后端服务 - 商品与购物车 API

技术栈：Python 3.11+ + FastAPI + SQLite
关键特性：
- 服务端验证：所有价格/库存从数据库读取，不信任客户端
- 幂等性：通过 Idempotency-Key 请求头保证重复请求不重复添加
- 并发安全：采用 SQLite 事务 + 乐观锁（UPDATE ... WHERE stock >= qty）防止超卖
- 结构化错误：统一 {error: {code, message}} 格式
"""

import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 数据库配置
# ---------------------------------------------------------------------------

# 使用基于 main.py 所在目录的绝对路径，确保工作目录变化时数据库文件位置稳定
# 支持通过 AERIS_DB_PATH 环境变量覆盖（主要用于测试）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("AERIS_DB_PATH", os.path.join(BASE_DIR, "app.db"))


def get_db_connection() -> sqlite3.Connection:
    """获取 SQLite 数据库连接。

    返回的连接启用了 WAL 模式以提升并发读性能，
    并设置 row_factory 为 sqlite3.Row 方便按列名访问。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL 模式：读操作不阻塞写，写操作不阻塞读（SQLite 并发优化）
    conn.execute("PRAGMA journal_mode=WAL")
    # 繁忙超时：当数据库被锁定时，等待最多 5 秒而不是立即报错
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# ---------------------------------------------------------------------------
# 数据初始化
# ---------------------------------------------------------------------------

def init_db() -> None:
    """初始化数据库表结构并填充 Seed 数据。

    数据表：
    - products: 商品基础信息
    - skus: 库存单位（颜色 x 尺寸）
    - cart_items: 购物车项
    - idempotency_keys: 幂等键存储（保存请求结果）

    Seed 数据设计：
    - 1 个产品：基础 T 恤
    - 7 个 SKU（3 种颜色 x 3 种尺寸，但 红色+XL 组合不存在）
    - 1 个缺货 SKU：白色 + XL（stock=0）
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- 建表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            image_url TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            color TEXT NOT NULL,
            size TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            image_url TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id),
            UNIQUE (product_id, color, size)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (sku_id) REFERENCES skus (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Seed 数据：仅在表为空时插入 ---
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO products (id, name, description, image_url) VALUES (?, ?, ?, ?)",
            (
                1,
                "基础T恤",
                "100% 纯棉经典圆领T恤，舒适透气，日常百搭。",
                "https://example.com/images/basic-tee.jpg",
            ),
        )

        # 7 个 SKU：3 色 x 3 码 = 9 组合，去掉 红色+XL（不可用组合）
        # 注意：白色+XL 设为 stock=0（缺货）
        skus_data = [
            # 黑色
            (1, "黑色", "S", 99.0, 20, "https://example.com/images/tee-black-s.jpg"),
            (1, "黑色", "M", 99.0, 15, "https://example.com/images/tee-black-m.jpg"),
            (1, "黑色", "L", 99.0, 10, "https://example.com/images/tee-black-l.jpg"),
            (1, "黑色", "XL", 109.0, 5, "https://example.com/images/tee-black-xl.jpg"),
            # 白色
            (1, "白色", "S", 99.0, 18, "https://example.com/images/tee-white-s.jpg"),
            (1, "白色", "M", 99.0, 12, "https://example.com/images/tee-white-m.jpg"),
            (1, "白色", "L", 99.0, 8, "https://example.com/images/tee-white-l.jpg"),
            (1, "白色", "XL", 109.0, 0, "https://example.com/images/tee-white-xl.jpg"),  # 缺货
            # 红色（缺 XL 码，模拟不可用组合）
            (1, "红色", "S", 109.0, 10, "https://example.com/images/tee-red-s.jpg"),
            (1, "红色", "M", 109.0, 7, "https://example.com/images/tee-red-m.jpg"),
            (1, "红色", "L", 109.0, 3, "https://example.com/images/tee-red-l.jpg"),
            # 红色+XL 不存在（不可用组合）
        ]
        cursor.executemany(
            "INSERT INTO skus (product_id, color, size, price, stock, image_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            skus_data,
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# FastAPI 应用生命周期
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库。"""
    init_db()
    yield


app = FastAPI(title="AerisHealth Cart API", version="1.0.0", lifespan=lifespan)

# CORS 配置：开发环境允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------

class AddCartItemRequest(BaseModel):
    """添加购物车项请求体。"""
    sku_id: int = Field(..., description="SKU ID")
    quantity: int = Field(..., gt=0, description="数量，必须大于 0")


class ErrorResponse(BaseModel):
    """统一错误响应格式。"""
    code: str
    message: str


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def make_error(code: str, message: str, status_code: int) -> HTTPException:
    """构造结构化错误的 HTTPException。

    采用 FastAPI 的 HTTPException，detail 字段为 {code, message} 字典，
    配合全局异常处理器返回统一格式。
    """
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """全局 HTTP 异常处理器，返回统一的 {error: {code, message}} 格式。"""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        content = {"error": {"code": detail["code"], "message": detail["message"]}}
    else:
        # 兼容 FastAPI 内置验证错误
        content = {"error": {"code": "invalid_input", "message": str(detail)}}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """请求参数验证错误处理器，将 Pydantic 验证错误转为 400 invalid_input。

    FastAPI/Pydantic 默认返回 422，这里统一为 400 invalid_input
    符合项目的错误码规范。
    """
    errors = exc.errors()
    # 提取第一个错误的字段和信息
    if errors:
        first_error = errors[0]
        loc = ".".join(str(x) for x in first_error.get("loc", []))
        msg = first_error.get("msg", "验证失败")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "请求参数验证失败"
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": {"code": "invalid_input", "message": message}},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底异常处理器，返回 500 internal_error。"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "服务器内部错误"}},
    )


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------

@app.get("/api/products/{product_id}")
def get_product(product_id: int) -> dict:
    """获取商品详情，包含选项维度和所有 SKU。

    返回结构：
    {
        product: {id, name, description, image_url},
        options: [{name, values: [...]}],
        skus: [...]
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 查询产品
    cursor.execute(
        "SELECT id, name, description, image_url FROM products WHERE id = ?",
        (product_id,),
    )
    product_row = cursor.fetchone()
    if not product_row:
        conn.close()
        raise make_error("product_not_found", "产品不存在", 404)

    product = {
        "id": product_row["id"],
        "name": product_row["name"],
        "description": product_row["description"],
        "image_url": product_row["image_url"],
    }

    # 查询所有 SKU
    cursor.execute(
        "SELECT id, product_id, color, size, price, stock, image_url "
        "FROM skus WHERE product_id = ?",
        (product_id,),
    )
    sku_rows = cursor.fetchall()
    skus = [
        {
            "id": row["id"],
            "product_id": row["product_id"],
            "color": row["color"],
            "size": row["size"],
            "price": row["price"],
            "stock": row["stock"],
            "image_url": row["image_url"],
        }
        for row in sku_rows
    ]

    # 从 SKU 中提取选项维度（颜色、尺寸的去重值列表）
    colors = sorted({sku["color"] for sku in skus})
    sizes = sorted({sku["size"] for sku in skus})
    options = [
        {"name": "color", "values": colors},
        {"name": "size", "values": sizes},
    ]

    conn.close()
    return {"product": product, "options": options, "skus": skus}


@app.post("/api/cart/items", status_code=200)
def add_to_cart(
    item: AddCartItemRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> dict:
    """添加 SKU 到购物车。

    关键实现要点：
    1. 幂等性：通过 Idempotency-Key 请求头实现，相同 key 重复请求返回相同结果
    2. 服务端验证：SKU 存在性、数量合法性、库存充足性全部从 DB 读取验证
    3. 并发安全：使用 SQLite 事务 + 乐观锁（UPDATE ... WHERE stock >= qty），
       通过检查 affected rows 判断是否扣减成功，防止超卖

    Args:
        item: 包含 sku_id 和 quantity 的请求体
        idempotency_key: 幂等键，从请求头 Idempotency-Key 读取

    Returns:
        购物车项信息
    """
    # --- 幂等键校验 ---
    if not idempotency_key or not idempotency_key.strip():
        raise make_error(
            "invalid_idempotency_key",
            "Idempotency-Key 请求头不能为空",
            400,
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 先检查幂等键是否已存在（快速路径）
        cursor.execute(
            "SELECT response_json, status_code FROM idempotency_keys WHERE key = ?",
            (idempotency_key,),
        )
        cached = cursor.fetchone()
        if cached:
            import json
            conn.close()
            return json.loads(cached["response_json"])

        # --- SKU 存在性校验 ---
        cursor.execute(
            "SELECT id, price, color, size, stock FROM skus WHERE id = ?",
            (item.sku_id,),
        )
        sku_row = cursor.fetchone()
        if not sku_row:
            conn.close()
            raise make_error("sku_not_found", "SKU 不存在", 404)

        # --- 数量合法性校验 ---
        if item.quantity <= 0:
            conn.close()
            raise make_error("invalid_input", "数量必须大于 0", 400)

        # --- 库存扣减（乐观锁 + 事务保证并发安全） ---
        # 关键决策：使用 UPDATE ... WHERE stock >= ? 的原子操作作为乐观锁。
        # SQLite 的 UPDATE 本身是原子的，通过检查 cursor.rowcount 可以判断
        # 是否成功扣减。如果并发请求同时扣减，只有第一个能成功（rowcount=1），
        # 后续请求会因 stock < qty 导致 WHERE 条件不满足（rowcount=0），
        # 从而返回库存不足，有效防止超卖。
        cursor.execute(
            "UPDATE skus SET stock = stock - ? WHERE id = ? AND stock >= ?",
            (item.quantity, item.sku_id, item.quantity),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            raise make_error("insufficient_stock", "库存不足", 400)

        # --- 添加到购物车 ---
        cursor.execute(
            "INSERT INTO cart_items (sku_id, quantity) VALUES (?, ?)",
            (item.sku_id, item.quantity),
        )
        cart_item_id = cursor.lastrowid

        # --- 记录幂等键 ---
        response_data = {
            "id": cart_item_id,
            "sku_id": item.sku_id,
            "quantity": item.quantity,
            "color": sku_row["color"],
            "size": sku_row["size"],
            "price": sku_row["price"],
        }
        import json
        cursor.execute(
            "INSERT INTO idempotency_keys (key, response_json, status_code) VALUES (?, ?, ?)",
            (idempotency_key, json.dumps(response_data), 200),
        )

        conn.commit()
        return response_data

    except HTTPException:
        # 已经是业务错误，直接抛出
        raise
    except Exception as e:
        conn.rollback()
        raise make_error("internal_error", f"服务器内部错误: {str(e)}", 500)
    finally:
        conn.close()


@app.get("/api/cart")
def get_cart() -> dict:
    """获取购物车详情，包含商品明细和总价。

    返回结构：
    {
        items: [{sku_id, quantity, color, size, price, name}],
        total_items: 总件数,
        total_price: 总价
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ci.id AS cart_item_id,
            ci.sku_id,
            ci.quantity,
            s.color,
            s.size,
            s.price,
            p.name
        FROM cart_items ci
        JOIN skus s ON ci.sku_id = s.id
        JOIN products p ON s.product_id = p.id
        ORDER BY ci.id
    """)
    rows = cursor.fetchall()

    items = []
    total_items = 0
    total_price = 0.0

    for row in rows:
        items.append({
            "sku_id": row["sku_id"],
            "quantity": row["quantity"],
            "color": row["color"],
            "size": row["size"],
            "price": row["price"],
            "name": row["name"],
        })
        total_items += row["quantity"]
        total_price += row["price"] * row["quantity"]

    conn.close()
    return {
        "items": items,
        "total_items": total_items,
        "total_price": round(total_price, 2),
    }


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> dict:
    """健康检查端点。"""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
    )
