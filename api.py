from config import *
from flask import *

from datetime import datetime
from openai import OpenAI

from sqlconnectormodule import *
import traceback
import threading
import requests
import telebot
import random
import string
import time
import json
import csv
import io
import os

bot = telebot.TeleBot(bot_token)

def ask_ai(messages=[], question="", context=""):
	openai_client = OpenAI(api_key=openai_token)
	model = "gpt-4-1106-preview"

	if not messages:
		if context:
			messages.append({"role": "user", "content": context})

		messages.append({"role": "user", "content": question})

	try:
		response = openai_client.chat.completions.create(
			model = model,
			messages = messages
		)
	except:
		return "error"

	ai_answer = response.choices[0].message.content[:4096]

	return ai_answer

def convert_number(number):
	return int(number)

def chunks(lst, n):
	for i in range(0, len(lst), n):
		yield lst[i:i + n]

def unix_to_month(t):
	return ' в '.join(datetime.fromtimestamp(t).strftime('%m.%Y').split())

def unix_to_day(t):
	return ' в '.join(datetime.fromtimestamp(t).strftime('%d.%m').split())

def unix_from_date(date):
	return time.mktime(datetime.strptime(date, "%Y-%m-%d").timetuple())

def execute_sql(q, *args, show_count=False, show_id=False, **kwargs):
	sql = SQL(mysql_host, mysql_user, mysql_password, mysql_db)
	r = sql.run(q, *args, **kwargs)
	if show_count:
		return sql.cursor.rowcount
	if show_id:
		return sql.run("SELECT last_insert_id()")[0][0]
	sql.close()
	return r

def gen_string(l=64):
	return ''.join([random.choice(string.ascii_lowercase + string.ascii_uppercase + '123456789') for _ in range(l)])

def escape_markdown(msg):
	return str(msg).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")

def arr_to_menu(menu):
	rm = telebot.types.ReplyKeyboardMarkup(True, one_time_keyboard=False)

	for btn in menu:
		if type(btn) == list:
			rm.row(*btn)
		else:
			rm.row(btn)

	return rm

def arr_to_inline(menu, markup=False):
	if not markup:
		markup = telebot.types.InlineKeyboardMarkup()
	for row in menu:
		row_ = []
		for btn in row:
			if 'link' in btn:
				row_.append(telebot.types.InlineKeyboardButton(text=btn["title"], url=btn["link"]))
			else:
				row_.append(telebot.types.InlineKeyboardButton(text=btn["title"], callback_data=btn["data"]))
		markup.add(*row_)
	return markup

def check_api_tokens(request):
	try:
		priority = execute_sql("SELECT priority FROM api_keys WHERE token=%s", request.headers.get("X-Token"))[0][0]
	except:
		priority = 0

	return {"priority" : priority}

