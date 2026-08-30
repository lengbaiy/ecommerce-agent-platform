import pytest

from app.llm.providers.bailian import BailianStructuredLLMClient


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"market":"US"}', {"market": "US"}),
        ('```json\n{"market":"US"}\n```', {"market": "US"}),
        ('提取结果如下：\n{"market":"US"}\n请确认。', {"market": "US"}),
        ('{"data":{"market":"US"}}', {"market": "US"}),
    ],
)
def test_decode_structured_content_accepts_common_bailian_formats(
    content: str,
    expected: dict[str, str],
) -> None:
    assert BailianStructuredLLMClient._decode_json_content(content) == expected


def test_decode_structured_content_rejects_non_json_response() -> None:
    with pytest.raises(ValueError):
        BailianStructuredLLMClient._decode_json_content("无法提取")
