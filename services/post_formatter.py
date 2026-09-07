def format_quote_post(quote: dict) -> str:
    author = quote.get("author", "Unknown")
    text = quote.get("text") or quote.get("quote", "")
    source = quote.get("source")
    link = quote.get("link")

    parts = [f'"{text}"', f"— {author}"]
    if source and source != "unknown":
        parts.append(source)
    if link and link != "No link provided":
        parts.append(link)

    message = "\n".join(parts)
    if len(message) > 280:
        # X hard limit; keep attribution when trimming
        trimmed = f'"{text[:200].rstrip()}…"\n— {author}'
        if link and link != "No link provided":
            trimmed = f"{trimmed}\n{link}"
        message = trimmed[:280]

    return message
