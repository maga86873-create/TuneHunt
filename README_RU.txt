TUNEHUNT BOT — инструкция для iPhone

ВАЖНО:
1. Никому не отправляй TELEGRAM_TOKEN или AUDD_TOKEN.
2. Токен Telegram, который ты ранее отправил в чат, нужно отозвать через @BotFather командой /revoke и выбрать своего бота. Используй только новый токен.
3. AudD — отдельный сервис; бесплатные лимиты могут меняться.
4. Render Free может останавливать сервис после простоя. Постоянная работа 24/7 не гарантируется.
5. Загрузка ссылок зависит от доступности платформы. Сохраняй только контент, который разрешено скачивать.

ФАЙЛЫ:
- main.py — код бота
- requirements.txt — зависимости
- render.yaml — настройки Render

ЗАПУСК:
1. Создай аккаунт GitHub и новый репозиторий tunehunt-bot.
2. В репозитории нажми Add file → Upload files и загрузи эти три файла.
3. Открой render.com и войди через GitHub.
4. Нажми New → Blueprint (если доступно) и выбери репозиторий.
   Если Blueprint недоступен: New → Web Service и укажи:
   Build Command: pip install -r requirements.txt && apt-get update && apt-get install -y ffmpeg
   Start Command: python main.py
5. В Environment добавь:
   TELEGRAM_TOKEN = новый токен BotFather
   AUDD_TOKEN = токен с dashboard.audd.io
6. Нажми Deploy.
7. После запуска открой Telegram-бота и отправь /start.

ПРОВЕРКА:
- Сначала отправь короткий аудио- или видеофайл.
- Затем попробуй публичную ссылку на видео.
- Если не работает, открой Logs в Render и найди последнюю ошибку.

ПРИМЕЧАНИЕ:
Этот проект использует polling Telegram и HTTP health endpoint. На бесплатном Render веб-сервис может засыпать, а polling может терять доступность во время сна. Тарифы и функции хостинга меняются.
