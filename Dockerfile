FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y python3-pymysql

COPY requirements.txt /app/requirements.txt

RUN python -m pip install -r requirements.txt

ENTRYPOINT ["python", "bot.py"]