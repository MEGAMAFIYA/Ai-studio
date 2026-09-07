#!/bin/bash

PID_FILE="bot.pid"
LOG_FILE="bot.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null; then
        echo "⚠️ Bot allaqachon ishlayapti (PID: $PID)."
        echo "To'xtatish uchun: kill $PID"
        exit 1
    else
        rm "$PID_FILE"
    fi
fi

echo "🚀 AI Studio bot fonda ishga tushirilmoqda..."

if [ -d "venv" ]; then
    source venv/bin/activate
fi

nohup python main.py > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "✅ Bot muvaffaqiyatli ishga tushdi! (PID: $(cat $PID_FILE))"
echo "Loglar: tail -f $LOG_FILE"
echo "To'xtatish: kill $(cat $PID_FILE)"
