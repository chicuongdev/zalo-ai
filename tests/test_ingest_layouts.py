"""Hand-kept sales book layouts found in the public test (structural rules, no shop-specific code)."""
import pandas as pd

from datamate.ingest.builder import _is_group_key, _split_adjustment_lines
from datamate.ingest.normalize import status_from_note


def test_order_number_on_first_row_only():
    df = pd.DataFrame({"line_no": [1, None, 2, None, None, 3],
                       "customer_name": ["A", None, "B", None, None, "C"],
                       "paid": [10, None, 20, None, None, 5]})
    assert _is_group_key(df, "line_no")


def test_order_number_repeated_on_every_row():
    df = pd.DataFrame({"line_no": [7, 7, 8, 9, 9, 9],
                       "customer_name": ["A (09)", "A - 09", "B", "C", "C", "C"],   # spelled differently
                       "paid": [10, 10, 20, 5, 5, 5]})
    assert _is_group_key(df, "line_no")


def test_running_row_number_is_not_an_order_key():
    df = pd.DataFrame({"line_no": [1, 2, 3, 4], "customer_name": ["A", "A", "B", "C"], "paid": [1, 1, 2, 3]})
    assert not _is_group_key(df, "line_no")


def test_status_from_note():
    assert status_from_note(None) == "completed"
    assert status_from_note("Huỷ") == "cancelled"
    assert status_from_note("khách mang trả") == "returned"
    assert status_from_note("trả lại hàng") == "returned"
    assert status_from_note("trả góp 6 tháng") == "completed"     # a payment, not a return
    assert status_from_note("khách trả trước 2tr") == "completed"
    assert status_from_note("đang giao") == "delivering"


def test_adjustment_rows_leave_goods_lines():
    orders = pd.DataFrame({"order_id": ["A", "B"]})
    lines = pd.DataFrame({"order_id": ["A", "A", "A", "B"],
                          "product_name": ["Sữa X", "Voucher", "Phí ship", "Dùng 200 điểm"],
                          "qty": [2, None, None, None], "line_amount": [100, -10, 25, -20]})
    o, l = _split_adjustment_lines(orders, lines, None, [])
    assert list(l["product_name"]) == ["Sữa X"]
    assert o.set_index("order_id")["order_discount"].to_dict() == {"A": 10, "B": 20}
    assert o.set_index("order_id")["shipping_fee"].to_dict() == {"A": 25, "B": 0}
