def has_limitations(text: str) -> bool:
    markers = ("局限", "失效", "不适用")
    return any(marker in text for marker in markers)


def within_model_count(count: int) -> bool:
    return 3 <= count <= 7
