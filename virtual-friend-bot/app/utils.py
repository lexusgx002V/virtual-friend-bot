def clamp_history(history: list, max_chars: int = 6000) -> list:
    """
    Ограничивает историю по суммарной длине символов,
    чтобы не переполнять контекст модели.
    """
    total = 0
    trimmed = []
    for m in reversed(history):  # начинаем с конца (последние сообщения важнее)
        c = len(m.get("content", ""))
        if total + c <= max_chars:
            trimmed.append(m)
            total += c
        else:
            break
    trimmed.reverse()
    return trimmed
