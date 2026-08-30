import json
import logging
import sys

from app.main import JsonFormatter


def test_json_formatter_includes_exception_details() -> None:
    try:
        raise ValueError("persistence failed")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="app.tools.product_search",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Product search persistence failed",
        args=(),
        exc_info=exc_info,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["exception_type"] == "ValueError"
    assert payload["exception"] == "persistence failed"
    assert "Traceback (most recent call last)" in payload["traceback"]
