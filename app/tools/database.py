"""Tool 3: database (high risk) - a fake in-memory list of 10 users, not a
real database, so delete_user() can be tested without ever touching real
data. Real PostgreSQL shows up in Part 6, and only for logs."""

_INITIAL_USERS = [
    {"id": 1, "name": "Alice Chen", "email": "alice@example.com"},
    {"id": 2, "name": "Bob Diaz", "email": "bob@example.com"},
    {"id": 3, "name": "Carla Reyes", "email": "carla@example.com"},
    {"id": 4, "name": "David Kim", "email": "david@example.com"},
    {"id": 5, "name": "Elena Novak", "email": "elena@example.com"},
    {"id": 6, "name": "Farid Hassan", "email": "farid@example.com"},
    {"id": 7, "name": "Grace Liu", "email": "grace@example.com"},
    {"id": 8, "name": "Hiro Tanaka", "email": "hiro@example.com"},
    {"id": 9, "name": "Ines Moreau", "email": "ines@example.com"},
    {"id": 10, "name": "Jack Turner", "email": "jack@example.com"},
]

_users = [dict(u) for u in _INITIAL_USERS]

_INITIAL_PRODUCTS = [
    {"id": 1, "name": "Wireless Mouse", "category": "electronics", "price": 25.0},
    {"id": 2, "name": "Bluetooth Speaker", "category": "electronics", "price": 60.0},
    {"id": 3, "name": "USB-C Cable", "category": "electronics", "price": 12.0},
    {"id": 4, "name": "Noise-Cancelling Headphones", "category": "electronics", "price": 150.0},
    {"id": 5, "name": "Webcam", "category": "electronics", "price": 45.0},
    {"id": 6, "name": "Novel: The Long Way", "category": "books", "price": 18.0},
    {"id": 7, "name": "Cookbook", "category": "books", "price": 22.0},
    {"id": 8, "name": "T-Shirt", "category": "clothing", "price": 15.0},
    {"id": 9, "name": "Running Shoes", "category": "clothing", "price": 80.0},
    {"id": 10, "name": "Coffee Mug", "category": "home", "price": 9.0},
]

_products = [dict(p) for p in _INITIAL_PRODUCTS]


def reset():
    global _users, _products
    _users = [dict(u) for u in _INITIAL_USERS]
    _products = [dict(p) for p in _INITIAL_PRODUCTS]


def list_users() -> list:
    return list(_users)


def read_user(user_id: int) -> dict:
    for u in _users:
        if u["id"] == user_id:
            return u
    return {"error": f"user {user_id} not found"}


def delete_user(user_id: int) -> dict:
    global _users
    before = len(_users)
    _users = [u for u in _users if u["id"] != user_id]
    if len(_users) == before:
        return {"error": f"user {user_id} not found"}
    return {"deleted": user_id}


def list_products() -> list:
    return list(_products)


def update_product_price(price: float, product_id: int = None, category: str = None) -> dict:
    """Set price on one product (product_id) or every product in a category.
    Same shape either way - the Safety Gate (app/safety/gate.py), not this
    function, is what tells a single-product update apart from a
    whole-category one."""
    if product_id is not None:
        for p in _products:
            if p["id"] == product_id:
                p["price"] = price
                return {"updated": [product_id], "price": price}
        return {"error": f"product {product_id} not found"}
    if category is not None:
        updated = [p["id"] for p in _products if p["category"] == category]
        for p in _products:
            if p["category"] == category:
                p["price"] = price
        if not updated:
            return {"error": f"no products in category '{category}'"}
        return {"updated": updated, "price": price}
    return {"error": "must specify product_id or category"}
