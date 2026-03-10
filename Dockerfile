FROM python:3.11-slim
RUN pip install pyTelegramBotAPI google-generativeai
COPY bot.py .
COPY *.txt .
CMD ["python", "bot.py"]
