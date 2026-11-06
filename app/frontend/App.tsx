import {useState, useEffect} from 'react'
import axios from 'axios'

interface Sku {
    id: number
    color: string
    size: string
    stock: number
}

interface Product {
    name: string
    skus: Sku[]
}

interface CartItem {
    sku_id: number
    quantity: number
}

export default function App() {
    const [product, setProduct] = useState<Product | null>(null)
    const [selectedSkuid, setSelectedSkuid] = useState<number | null>(null)
    const [cart, setCart] = useState<CartItem[]>([])

    useEffect(() => {
        axios.get('[http://localhost:8000/api/product/1](http://localhost:8000/api/product/1)')
            .then(res => setProduct(res.data))
        axios.get('[http://localhost:8000/api/cart](http://localhost:8000/api/cart)')
            .then(res => setCart(res.data))
    }, [])

    const addToCart = async () => {
        if (!selectedSkuid) return
        await axios.post('[http://localhost:8000/api/cart/items](http://localhost:8000/api/cart/items)', { sku_id: selectedSkuid })
        const res = await axios.get('[http://localhost:8000/api/cart](http://localhost:8000/api/cart)')
        setCart(res.data.items)
    }

    return (

        <div style={{ padding: '20px' }}>
            <div>
                <button onClick={addToCart} disabled={!selectedSkuid} style={{ marginTop: '20px' }}>
                    加购
                </button>
                <h3>购物车</h3>
                {cart.map((item, idx) => (
                    <div key={idx}>SKU ID:{item.sku_id} 数量:{item.quantity}</div>
                ))}
            </div>
        </div>
    )
}