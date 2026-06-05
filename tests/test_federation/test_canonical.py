import pytest

from app.federation.canonical import jcs_bytes


def test_jcs_orders_keys_and_strips_whitespace():
    # RFC 8785: lexicographic key order, no insignificant whitespace, UTF-8
    assert jcs_bytes({"b": 1, "a": "ü"}) == '{"a":"ü","b":1}'.encode()


def test_jcs_is_stable_across_dict_insertion_order():
    assert jcs_bytes({"x": [2, 1], "a": True}) == jcs_bytes(
        dict([("a", True), ("x", [2, 1])])
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        ({"a": 1, "b": 2}, '{"a":1,"b":2}'),  # int passthrough
        ({"n": 0}, '{"n":0}'),
        ({"n": -0.0}, '{"n":0}'),  # negative zero -> "0"
        ({"n": 1.0}, '{"n":1}'),  # integral float -> "1"
        ({"n": 4.50}, '{"n":4.5}'),  # trailing zero stripped
        ({"n": 0.002}, '{"n":0.002}'),  # 2e-3 -> 0.002 (n=-2, fixed)
        ({"n": 1e30}, '{"n":1e+30}'),  # large -> exponential, e+30
        ({"n": 1e-7}, '{"n":1e-7}'),  # n=-6 boundary -> exponential
        ({"n": 1e21}, '{"n":1e+21}'),  # n=21 boundary: 1e+21 (n>21 region)
        ({"n": 1e20}, '{"n":100000000000000000000}'),  # n=21 -> fixed (k<=n<=21)
        ({"n": 333333333.33333329}, '{"n":333333333.3333333}'),
        ({"n": 1e-27}, '{"n":1e-27}'),
        ({"t": True, "f": False, "z": None}, '{"f":false,"t":true,"z":null}'),
        ({"s": 'a/b"c'}, '{"s":"a/b\\"c"}'),  # quote escaped; solidus NOT escaped
        ({"arr": [3, 2.5, "x"]}, '{"arr":[3,2.5,"x"]}'),
    ],
)
def test_jcs_rfc8785_official_vectors(value, expected):
    assert jcs_bytes(value) == expected.encode("utf-8")
