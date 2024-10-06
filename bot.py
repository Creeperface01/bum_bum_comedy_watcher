import logging
import os
import pymysql

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackContext
import requests
from bs4 import BeautifulSoup, Tag
import itertools

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    link = Column(String(255))

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    telegram_id = Column(Integer, unique=True)

mysql_user = os.environ.get('MYSQL_USER')
mysql_password = os.environ.get('MYSQL_PASSWORD')
mysql_database = os.environ.get('MYSQL_DATABASE')

engine = create_engine('mysql+pymysql://%s:%s@db:3306/%s' % (mysql_user, mysql_password, mysql_database))

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session.add(User(
        name=update.message.from_user.name,
        telegram_id=update.message.chat_id
    ))
    session.commit()

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Started watching"
    )


async def check_webside(context: CallbackContext):
    response = requests.get('https://bumbumcomedy.cz/')

    if response.status_code != 200:
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    tables = soup.select('.vc_tta-panels div.vc_tta-panel-body:has(a[itemprop="url"])')

    data = list(itertools.chain(*map(lambda x: process_table(x), tables)))

    (added_events, deleted_events) = compare_data_with_db(data)

    if len(added_events) != 0:
        await message_users(
            context,
            'New events:\n%s' % '\n\n'.join(
                map(lambda x: '%s - Buy ticket at: %s' % (x['text'], x['link']), added_events)
            ),
        )

    if len(deleted_events) != 0:
        await message_users(
            context,
            'Deleted events:\n%s' % '\n'.join(deleted_events),
        )

    events_to_delete = session.query(Event).filter(Event.name.in_(deleted_events)).all()
    for event in events_to_delete:
        session.delete(event)


    for event in added_events:
        session.add(Event(
            name=event['text'],
            link=event['link'],
        ))

    session.commit()


async def message_users(context: CallbackContext, message: str):
    users = session.query(User).all()

    for user in users:
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=message,
        )


def compare_data_with_db(data: list[dict[str, str]]) -> (list[dict[str, str]], list[str]):
    event_names = list(map(lambda x: x['text'], data))
    stored_event_names = list(map(lambda x: x.name, session.query(Event).all()))

    deleted_events = list(filter(lambda x: x not in event_names, stored_event_names))
    added_events = list(filter(lambda x: x['text'] not in stored_event_names, data))

    return added_events, deleted_events


def process_table(table: Tag) -> list[dict[str, str]]:
    links = table.select('div a[href*="bumbum.koupitvstupenku.cz/?idperf"]')

    row_data = []

    for link in links:
        row_data.append({
            'link': link['href'],
            'text': link.get_text(strip=True),
        })

    return row_data

if __name__ == '__main__':
    application = ApplicationBuilder().token(os.environ.get('TELEGRAM_TOKEN')).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(check_webside, interval=60, first=10)

    application.run_polling()