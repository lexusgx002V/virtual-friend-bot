import os
import httpx
import asyncio

PROVIDER = os.getenv("LLM_PROVIDER", "openai")

# Простой адаптер под чат LLM. Можно заменить на любой API.
# История и системное сообщение передаются в стиле OpenAI Chat API.

async def chat_completion(system_prompt: str, history: list, user_text: str) -> str:
    if PROVIDER == "openai":
        return await _openai_chat(system_prompt, history, user_text)
    # Заглушка: можно добавить другие провайдеры (Anthropic, OpenRouter, локальная модель)
    return "Привет! Я пока не настроен на другой провайдер. Попроси разработчика указать OPENAI_API_KEY в .env."

async def _openai_chat(system_prompt: str, history: list, user_text: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        return "Нужен OPENAI_API_KEY в .env, чтобы я мог отвечать умно 😅"

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": user_text})

    # Важно: не храните ключи в логах.
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 500
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code != 200:
            return f"LLM ошибка: {r.status_code} {r.text}"
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return "Не удалось разобрать ответ модели 😕"
