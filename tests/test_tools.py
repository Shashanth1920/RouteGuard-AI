"""No real API calls: search is tested against a fake requests.post response."""
import requests

from app.tools import calculator, database, search as search_tool
from app.tools.registry import TOOLS

# --- calculator ---------------------------------------------------------

def test_calculator_basic_multiplication():
    assert calculator.calculate("847 * 23") == {"result": 19481, "error": None}


def test_calculator_rejects_import():
    result = calculator.calculate("__import__('os').system('rm -rf /')")
    assert result["result"] is None
    assert result["error"] == "invalid expression"


def test_calculator_rejects_attribute_and_call_access():
    for expr in ["().__class__", "open('x')", "[1,2,3][0]"]:
        result = calculator.calculate(expr)
        assert result["result"] is None
        assert result["error"] == "invalid expression"


def test_calculator_division_by_zero_is_a_clean_error():
    result = calculator.calculate("1 / 0")
    assert result["result"] is None
    assert result["error"] == "division by zero"


def test_calculator_rejects_huge_exponent_instead_of_hanging():
    # 2**999999999999 is valid arithmetic but its bigint result would eat
    # unbounded memory/CPU - confirmed live, it grew a process to several GB.
    result = calculator.calculate("2 ** 999999999999")
    assert result["result"] is None
    assert result["error"] == "invalid expression"


# --- search --------------------------------------------------------------

class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_search_formats_fake_response(monkeypatch):
    fake_data = {
        "results": [
            {"title": "A", "content": "snippet A", "url": "http://a.com"},
            {"title": "B", "content": "snippet B", "url": "http://b.com"},
            {"title": "C", "content": "snippet C", "url": "http://c.com"},
            {"title": "D", "content": "snippet D", "url": "http://d.com"},
        ]
    }
    monkeypatch.setattr(
        search_tool.requests, "post",
        lambda *a, **k: FakeResponse(fake_data),
    )
    result = search_tool.search("test query")
    assert result["error"] is None
    assert len(result["results"]) == 3
    assert result["results"][0] == {"title": "A", "snippet": "snippet A", "link": "http://a.com"}


def test_search_failure_returns_clean_error(monkeypatch):
    def _raise(*a, **k):
        raise requests.ConnectionError("no network")
    monkeypatch.setattr(search_tool.requests, "post", _raise)
    result = search_tool.search("test query")
    assert result == {"results": [], "error": "search failed"}


# --- database --------------------------------------------------------------

def test_database_delete_then_reset():
    database.reset()
    assert database.read_user(3)["name"] == "Carla Reyes"
    deleted = database.delete_user(3)
    assert deleted == {"deleted": 3}
    assert database.read_user(3) == {"error": "user 3 not found"}
    database.reset()
    assert database.read_user(3)["name"] == "Carla Reyes"
    assert len(database.list_users()) == 10


def test_database_delete_unknown_user_is_a_clean_error():
    database.reset()
    assert database.delete_user(999) == {"error": "user 999 not found"}


def test_update_product_price_single_product():
    database.reset()
    result = database.update_product_price(price=50, product_id=1)
    assert result == {"updated": [1], "price": 50}
    assert database.list_products()[0]["price"] == 50
    database.reset()


def test_update_product_price_whole_category():
    database.reset()
    result = database.update_product_price(price=0, category="electronics")
    electronics_ids = [p["id"] for p in database.list_products() if p["category"] == "electronics"]
    assert set(result["updated"]) == set(electronics_ids)
    assert all(p["price"] == 0 for p in database.list_products() if p["category"] == "electronics")
    database.reset()


def test_update_product_price_unknown_product_is_a_clean_error():
    database.reset()
    assert database.update_product_price(price=10, product_id=999) == {"error": "product 999 not found"}


def test_update_product_price_unknown_category_is_a_clean_error():
    database.reset()
    assert database.update_product_price(price=10, category="nope") == {"error": "no products in category 'nope'"}


def test_update_product_price_needs_a_target():
    assert database.update_product_price(price=10) == {"error": "must specify product_id or category"}


# --- registry --------------------------------------------------------------

def test_registry_marks_delete_user_destructive():
    entry = next(t for t in TOOLS if t["name"] == "delete_user")
    assert entry["destructive"] is True
    assert entry["risk"] == "high"


def test_registry_every_tool_has_a_risk_label():
    for tool in TOOLS:
        assert tool["risk"] in ("low", "medium", "high")
        assert tool["description"]
