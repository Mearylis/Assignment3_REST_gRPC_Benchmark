"""Common deterministic business logic shared by REST and gRPC microservices."""
def lookup_item(item_id: int) -> dict:
    if not 1 <= item_id <= 100:
        return {"id": item_id, "name": "", "category": "", "stock": 0, "ok": False}
    return {
        "id": item_id,
        "name": f"Campus item {item_id:03d}",
        "category": ("hardware", "stationery", "books")[item_id % 3],
        "stock": (item_id * 7) % 101,
        "ok": True,
    }
