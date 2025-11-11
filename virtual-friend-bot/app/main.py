import asyncio
import os
import logging
import httpx
from io import BytesIO
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv

from app.memory import Memory
from app.personas import get_system_prompt, list_personas, list_modes
from app.llm_client import chat_completion
from app.utils import clamp_history

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("virtual-friend")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()
mem = Memory(db_path=os.getenv("DB_PATH", "friend.db"))

WELCOME = (
    "Привет! Я твой виртуальный друг. Напиши, как тебя звать, и чем я могу помочь сегодня.\n\n"
    "Команды:\n"
    "/persona — выбрать характер друга\n"
    "/mode — выбрать стиль общения\n"
    "/reset — очистить память беседы\n"
    "/help — подсказка\n"
)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    mem.ensure_user(user_id)
    await message.answer(WELCOME)

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(WELCOME)

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    mem.reset_dialog(user_id)
    await message.answer("Память диалога очищена. О чём поговорим?")

@dp.message(Command("persona"))
async def cmd_persona(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        personas = ", ".join(list_personas())
        await message.answer(
            f"Текущая персона: {mem.get_user(user_id)['persona']}\n"
            f"Доступны: {personas}\n"
            f"Пример: /persona friendly"
        )
        return
    choice = args[1].strip().lower()
    if choice not in list_personas():
        await message.answer(f"Неизвестная персона. Доступны: {', '.join(list_personas())}")
        return
    mem.set_persona(user_id, choice)
    await message.answer(f"Готово! Персона изменена на: {choice}")

@dp.message(Command("mode"))
async def cmd_mode(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        modes = ", ".join(list_modes())
        await message.answer(
            f"Текущий режим: {mem.get_user(user_id)['mode']}\n"
            f"Доступны: {modes}\n"
            f"Пример: /mode motivational"
        )
        return
    choice = args[1].strip().lower()
    if choice not in list_modes():
        await message.answer(f"Неизвестный режим. Доступны: {', '.join(list_modes())}")
        return
    mem.set_mode(user_id, choice)
    await message.answer(f"Режим изменён на: {choice}")

@dp.message(F.voice)
async def on_voice(message: Message):
    # 0) опционально: выключено ли STT
    if os.getenv("ENABLE_STT", "false").lower() != "true":
        await message.answer("Распознавание голоса выключено (ENABLE_STT=false).")
        return

    # 1) Скачиваем voice из Telegram -> bytes
    tg_file = await bot.get_file(message.voice.file_id)
    buf = BytesIO()
    await bot.download_file(tg_file.file_path, buf)
    buf.seek(0)
    audio_bytes = buf.getvalue()
    if not audio_bytes:
        await message.answer("Не удалось получить аудио.")
        return

    # 2) Отправляем в OpenAI на распознавание
    text = await openai_stt(audio_bytes)   # <--- эта строка ДОЛЖНА быть внутри функции!
    if not text:
        await message.answer("Не удалось распознать голос 🙁 Возможно, VPN блокирует API.")
        return

    # 3) Профиль и история
    user_id = message.from_user.id
    profile = mem.get_user(user_id)
    history = mem.get_history(user_id, limit=18)
    history = clamp_history(history, max_chars=6000)

    system_prompt = get_system_prompt(
        profile['persona'],
        profile['mode'],
        profile.get('name')
    )

    # 4) Генерим ответ
    reply = await chat_completion(system_prompt, history, text)  # <--- await внутри функции
    mem.add_message(user_id, "user", text)
    mem.add_message(user_id, "assistant", reply)

    # 5) Отправляем текст
    await message.answer(f"Распознал: {text}\n\n{reply}")

    # 6) Если включён TTS — озвучиваем
    if os.getenv("ENABLE_TTS", "false").lower() == "true":
        audio_reply = await openai_tts(reply)
        if audio_reply:
            await message.answer_audio(
                BufferedInputFile(audio_reply, filename="reply.mp3"),
                caption=reply[:1000]
            )


@dp.message(F.text)
async def on_text(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # …(логика с именем)…

    profile = mem.get_user(user_id)
    history = mem.get_history(user_id, limit=18)
    history = clamp_history(history, max_chars=6000)

    system_prompt = get_system_prompt(
        profile['persona'],
        profile['mode'],
        profile.get('name')
    )

    reply = await chat_completion(system_prompt, history, text)  # <--- тоже внутри функции
    mem.add_message(user_id, "user", text)
    mem.add_message(user_id, "assistant", reply)

    await message.answer(reply)

    if os.getenv("ENABLE_TTS", "false").lower() == "true":
        audio_bytes = await openai_tts(reply)
        if audio_bytes:
            await message.answer_audio(
                BufferedInputFile(audio_bytes, filename="reply.mp3"),
                caption=reply[:1000]
            )
# ---------- TTS: озвучка текста -> MP3 ----------
async def openai_tts(text: str) -> bytes | None:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        return None

    url = f"{base_url}/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text[:500],   # ограничим длину озвучки
        "voice": "alloy",      # можно: verse, amber, coral и др.
        "format": "mp3",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        # подсказка в лог, чтобы понимать, если VPN/регион блокирует
        print("TTS ERROR:", r.status_code, r.text)
        return None
    return r.content  # MP3-байты


# ---------- STT: распознавание голоса -> текст ----------
async def openai_stt(audio_bytes: bytes) -> str | None:
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("STT_MODEL", "gpt-4o-mini-transcribe")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        return None

    url = f"{base_url}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {
        "file": ("voice.ogg", audio_bytes, "audio/ogg"),
        "model": (None, model),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, files=files)
    if r.status_code != 200:
        print("STT ERROR:", r.status_code, r.text)
        return None
    data = r.json()
    return (data.get("text") or "").strip() or None

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
