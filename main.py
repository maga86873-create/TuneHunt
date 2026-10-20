import os
import re
import glob
import tempfile
import threading
import subprocess
from urllib.parse import urlparse

import requests
import yt_dlp
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
AUDD_TOKEN = os.getenv("AUDD_TOKEN", "")
PORT = int(os.getenv("PORT", "10000"))

MAX_VIDEO_MB = 45
MAX_TELEGRAM_MB = 19
URL_PATTERN = re.compile(r"https?://[^\s<>]+")

ALLOWED_DOMAINS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    "pinterest.com", "www.pinterest.com", "pin.it",
}

web = Flask(__name__)

@web.get("/")
def home():
    return "TuneHunt bot is running."

@web.get("/health")
def health():
    return {"ok": True}

def valid_url(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and any(
            host == domain or host.endswith("." + domain)
            for domain in ALLOWED_DOMAINS
        )
    except Exception:
        return False

def download_video(url, folder):
    options = {
        "outtmpl": os.path.join(folder, "video.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "max_filesize": MAX_VIDEO_MB * 1024 * 1024,
        "socket_timeout": 20,
        "retries": 1,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)
    files = [
        p for p in glob.glob(os.path.join(folder, "video.*"))
        if os.path.isfile(p) and not p.endswith(".part")
    ]
    if not files:
        raise RuntimeError("No video downloaded")
    path = max(files, key=os.path.getsize)
    if os.path.getsize(path) > MAX_VIDEO_MB * 1024 * 1024:
        raise RuntimeError("Video too large")
    return path

def extract_audio(video_path, folder):
    audio_path = os.path.join(folder, "clip.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-t", "12", "-vn",
         "-ac", "1", "-ar", "44100", "-b:a", "96k", audio_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, timeout=60,
    )
    if not os.path.exists(audio_path):
        raise RuntimeError("Audio extraction failed")
    return audio_path

def recognize_music(audio_path):
    if not AUDD_TOKEN:
        raise RuntimeError("AUDD_TOKEN is missing")
    if os.path.getsize(audio_path) > 10 * 1024 * 1024:
        raise RuntimeError("Audio exceeds AudD's 10 MB limit")
    with open(audio_path, "rb") as audio:
        response = requests.post(
            "https://api.audd.io/",
            data={"api_token": AUDD_TOKEN, "return": "spotify,apple_music"},
            files={"file": ("clip.mp3", audio, "audio/mpeg")},
            timeout=45,
        )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "success":
        raise RuntimeError("AudD returned an error")
    return data.get("result")

def format_song(song):
    if not song:
        return "😕 Не смог найти песню. Попробуй другой фрагмент, где музыка слышна отчётливо."
    title = song.get("title", "Неизвестный трек")
    artist = song.get("artist", "Неизвестный исполнитель")
    lines = [f"🎵 {title}", f"👤 {artist}"]
    if song.get("album"):
        lines.append(f"💿 {song['album']}")
    if song.get("song_link"):
        lines.append(f"🔎 Ссылка на трек: {song['song_link']}")
    spotify = song.get("spotify")
    if isinstance(spotify, dict):
        link = spotify.get("external_urls", {}).get("spotify")
        if link:
            lines.append(f"Spotify: {link}")
    apple = song.get("apple_music")
    if isinstance(apple, dict) and apple.get("url"):
        lines.append(f"Apple Music: {apple['url']}")
    return "\n".join(lines)

async def send_song(message, audio_path):
    await message.reply_text("🎧 Ищу музыку...")
    try:
        song = recognize_music(audio_path)
        await message.reply_text(format_song(song), disable_web_page_preview=True)
    except Exception as exc:
        print("Recognition error:", repr(exc))
        await message.reply_text(
            "Не получилось распознать музыку. Проверь ключ AudD и лимит запросов, "
            "затем попробуй ещё раз."
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Привет! Я TuneHunt — бот для поиска музыки.\n\n"
        "• Отправь видео или аудио файлом — попробую определить трек.\n"
        "• Отправь ссылку на YouTube, TikTok или Pinterest — попробую распознать музыку.\n"
        "• /download ССЫЛКА — сохранить доступное видео.\n"
        "• /help — помощь.\n\n"
        "Скачивай только контент, который тебе разрешено сохранять."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться:\n"
        "1) Отправь видео или аудиофайл.\n"
        "2) Или отправь ссылку на поддерживаемый ролик.\n"
        "3) Для скачивания доступного видео: /download https://...\n\n"
        "Приватные ролики и некоторые ссылки могут не работать. "
        "Размеры ограничены."
    )

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    media = message.video or message.audio or message.document
    if not media:
        return
    size = getattr(media, "file_size", None)
    if size and size > MAX_TELEGRAM_MB * 1024 * 1024:
        await message.reply_text("Файл слишком большой. Максимум — около 19 МБ.")
        return
    mime = getattr(media, "mime_type", "") or ""
    is_video = bool(message.video) or mime.startswith("video/")
    is_audio = bool(message.audio) or mime.startswith("audio/")
    if not is_video and not is_audio:
        await message.reply_text("Отправь аудио или видеофайл.")
        return
    with tempfile.TemporaryDirectory() as folder:
        try:
            tg_file = await media.get_file()
            source = os.path.join(folder, "source")
            await tg_file.download_to_drive(custom_path=source)
            audio = extract_audio(source, folder) if is_video else source
            await send_song(message, audio)
        except Exception as exc:
            print("Media error:", repr(exc))
            await message.reply_text("Не смог обработать файл. Попробуй другое видео или аудио.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match = URL_PATTERN.search(update.message.text or "")
    if not match:
        await update.message.reply_text("Пришли видео, аудио или ссылку.")
        return
    url = match.group(0).rstrip(".,!?) ]")
    if not valid_url(url):
        await update.message.reply_text("Поддерживаются ссылки на YouTube, TikTok и Pinterest.")
        return
    await update.message.reply_text("⏳ Проверяю ссылку и ищу музыку...")
    with tempfile.TemporaryDirectory() as folder:
        try:
            video = download_video(url, folder)
            audio = extract_audio(video, folder)
            await update.message.reply_text(format_song(recognize_music(audio)))
        except Exception as exc:
            print("Link error:", repr(exc))
            await update.message.reply_text(
                "Не получилось обработать ссылку. Видео может быть закрытым, "
                "недоступным для загрузки или сайт может блокировать доступ."
            )

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /download https://ссылка-на-видео")
        return
    url = context.args[0].rstrip(".,!?) ]")
    if not valid_url(url):
        await update.message.reply_text("Пришли ссылку на YouTube, TikTok или Pinterest.")
        return
    await update.message.reply_text("⏳ Загружаю доступное видео...")
    with tempfile.TemporaryDirectory() as folder:
        try:
            video = download_video(url, folder)
            await update.message.reply_text("📤 Отправляю видео...")
            with open(video, "rb") as file:
                await update.message.reply_document(
                    document=file, filename=os.path.basename(video),
                    read_timeout=120, write_timeout=120
                )
        except Exception as exc:
            print("Download error:", repr(exc))
            await update.message.reply_text(
                "Не удалось скачать видео. Возможно, ссылка недоступна или сайт "
                "ограничивает загрузку. Сохраняй только контент, на который есть разрешение."
            )

def run_web():
    web.run(host="0.0.0.0", port=PORT)

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Добавь TELEGRAM_TOKEN в переменные окружения.")
    if not AUDD_TOKEN:
        raise RuntimeError("Добавь AUDD_TOKEN в переменные окружения.")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.Document.ALL, handle_media
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    threading.Thread(target=run_web, daemon=True).start()
    print("TuneHunt запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
