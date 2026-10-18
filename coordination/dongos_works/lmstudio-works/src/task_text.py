def collapse_whitespace(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a str")
    return " ".join(text.split())
