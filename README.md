# AI Studio Telegram Bot

Kinolarni yuklab olib, ulardagi nutqni matnga aylantiradi va o'zbek tiliga tarjima qilib `.srt` subtitr fayli ko'rinishida qaytaradi.

## O'rnatish (Termux / Telefon)
1. `pkg install python git ffmpeg -y`
2. `git clone <repo_url>` va `cd ai_studio_bot`
3. `python -m venv venv && source venv/bin/activate`
4. `pip install -r requirements.txt`
5. `.env` faylini yarating va kalitlarni kiriting.
6. Ishga tushirish: `chmod +x run_bot.sh && ./run_bot.sh`

## Deploy (Render.com)
1. GitHub'ga yuklang (`.env` dan tashqari).
2. Render'da "Web Service" yarating.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py`
5. Environment Variables ga `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY`, `ADMIN_ID` ni kiriting.
