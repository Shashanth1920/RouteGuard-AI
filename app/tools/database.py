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


def reset():
    global _users
    _users = [dict(u) for u in _INITIAL_USERS]


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
