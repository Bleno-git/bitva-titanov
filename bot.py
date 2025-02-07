from api import *

openai_client = OpenAI(api_key=openai_token)

########################################################

def reply(message, *args, **kwargs):
	return bot.send_message(message.from_user.id, *args, **kwargs)

def main_menu(message):
	link = f'https://{project_domain}/dashboard/'
	webApp = telebot.types.WebAppInfo(link)
	keyboard = telebot.types.InlineKeyboardMarkup()
	keyboard.add(telebot.types.InlineKeyboardButton(text='📋 Открыть дашборд', web_app=webApp))
	keyboard.add(telebot.types.InlineKeyboardButton(text='🔥 Перейти на сайт', url=link))

	reply(message, "Можете посмотреть сводные графики, нажав на одну из кнопок ниже (приложение в телеграмме может отображаться неверно, переходите на сайт):", reply_markup=keyboard)

	month_start = time.mktime(datetime(month=int(datetime.now().strftime('%m')), year=int(datetime.now().strftime('%Y')), day=1).timetuple())
	last_month_start = time.mktime(datetime(month=int(datetime.now().strftime('%m'))-1, year=int(datetime.now().strftime('%Y')), day=1).timetuple())
	prelast_month_start = time.mktime(datetime(month=int(datetime.now().strftime('%m'))-2, year=int(datetime.now().strftime('%Y')), day=1).timetuple())

	this_month = dict(execute_sql("SELECT cargo_type, sum(total_costs)/sum(total_revenue)*100 from fact_finances_cargo_type where unload_day > %s group by cargo_type order by cargo_type;", month_start))
	last_month = dict(execute_sql("SELECT cargo_type, sum(total_costs)/sum(total_revenue)*100 from fact_finances_cargo_type where unload_day > %s and unload_day < %s group by cargo_type order by cargo_type;", last_month_start, month_start))

	reply(message, """Добро пожаловать в главное меню

*Можете попробовать отправить боту следующие запросы (протестированы):*
1) Покажи грузооборот за февраль по неделям
2) Покажи прибыль за 12 месяцев по месяцам
3) Тенденция расходов за март

В целом, бот поддерживает любые срезы, основные параметры, которые он может считать:
1) Грузооборот (кол-во зерна, отгруженного за определённый период)
2) Выручка (вес груза, умноженный на стоимость)
3) Расходы на транспортировку (учитывает все расходы)
4) Операционную прибыль (выручка - транспортные расходы)

Бот может создать график за любой период, указанный обычным текстом, сгруппировав данные по дням, неделям, месяцам.
Можно отправлять аудио сообщения, бот их так же поймёт.
""", reply_markup=arr_to_menu([
		['📱 О боте'],
		['📋 Статистика'],
		['💰 Выручка по месяцам 2024 год', '💱 Прибыль за этот месяц'],
		['📦 Грузооборот по месяцам 2024 год', '🍇 Выручка за март']
	]), parse_mode='MarkDown')

	avg_dt_this_month = execute_sql("SELECT avg(unload_time-load_time)/86400 from archive where unload_time-load_time>0 and unload_time > %s;", month_start)[0][0]
	avg_dt_that_month = execute_sql("SELECT avg(unload_time-load_time)/86400 from archive where unload_time-load_time>0 and unload_time > %s and unload_time < %s", last_month_start, month_start)[0][0]

	total_count_this_month = execute_sql("SELECT count(*) from archive where unload_time > %s;", month_start)[0][0]
	total_count_that_month = execute_sql("SELECT count(*) from archive where unload_time > %s AND unload_time < %s;", last_month_start, month_start)[0][0]
	total_count_prelast_month = execute_sql("SELECT count(*) from archive where unload_time > %s AND unload_time < %s;", prelast_month_start, last_month_start)[0][0]
	total_count_delta1 = (total_count_this_month - total_count_that_month) / total_count_that_month * 100
	total_count_delta2 = (total_count_that_month - total_count_prelast_month) / total_count_prelast_month * 100

	msg = f"""*Всего перевозок в этом месяце:* `{total_count_this_month}`шт. (`{round(total_count_delta1, 2)}`%)
*Всего перевозок в том месяце:* `{total_count_that_month}`шт. (`{round(total_count_delta2, 2)}`%)
*Всего перевозок в месяце до этого:* `{total_count_prelast_month}`шт. 

*Доля транспортных расходов от выручки:*
Этот месяц / прошлый месяц
*Соя:* `{round(this_month['соя'], 2)}`% (`{round(last_month['соя'], 2)}`%)
*Ячмень:* `{round(this_month['ячмень'], 2)}`% (`{round(last_month['ячмень'], 2)}`%)
*Кукуруза:* `{round(this_month['кукуруза'], 2)}`% (`{round(last_month['кукуруза'], 2)}`%)

*Средняя длительность доставки:*
*В этом месяце:* `{round(avg_dt_this_month, 2)}` д.
*В том месяце:* `{round(avg_dt_that_month, 2)}` д.



"""
	reply(message, msg, parse_mode="MarkDown")


@bot.message_handler(func=lambda m: m.text == "/start")
def start_handler(message):
	if not execute_sql("SELECT count(*) from users where telegram_id=%s", message.from_user.id)[0][0]:
		execute_sql("INSERT INTO users(telegram_id, nickname, joined, is_admin) values(%s, %s, unix_timestamp(), 0)", message.from_user.id, message.from_user.username)
	main_menu(message)

@bot.message_handler(func=lambda m: m.text == "📱 О боте")
def about_handler(message):
	reply(message, f"""Этот бот создан для обработки сырых данных и создания сводной статистики. Может обрабатывать человеческий текст в любом формате, в том числе аудио сообщения. Для тестирования, просто отправьте текст: `Покажи прибыль за февраль этого года`
Дашборд на сайте: https://{project_domain}/
Документация по API: https://{project_domain}/api/
""", parse_mode="MarkDown")

@bot.message_handler(func=lambda m: m.text == "📋 Статистика")
def stats_handler(message):
	users_in_bot = execute_sql("SELECT count(*) FROM users")[0][0]
	orders = execute_sql("SELECT count(*) FROM archive")[0][0]

	reply(message, f"""*Статистика бота:*
*Пользователей в боте:* `{users_in_bot}`
*Всего строчек данных:* `{orders}`
""", parse_mode="MarkDown")

def send_chart(message, query):
	link = f"https://{project_domain}/chart/%s" % query

	threading.Thread(target=requests.get, args=(link,), daemon=True).start()

	msg = reply(message, f"Ваш запрос: *{query}*.\n\nДанные будут готовы через несколько секунд...", parse_mode='MarkDown')

	time.sleep(2)
	bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)

	webApp = telebot.types.WebAppInfo(link)
	keyboard = telebot.types.InlineKeyboardMarkup()
	keyboard.add(telebot.types.InlineKeyboardButton(text='📋 Открыть дашборд', web_app=webApp))
	keyboard.add(telebot.types.InlineKeyboardButton(text='🔥 Перейти на сайт', url=link))

	reply(message, f"Ваш запрос: *{query}*\n\nВаши данные готовы, можете посмотреть графики:", reply_markup=keyboard, parse_mode="MarkDown")


@bot.message_handler(func=lambda m: True)
def unknown_text_handler(message):
	query = message.text

	if query.startswith('/') or len(query) < 10:
		return reply(message, "Команда не распознана, попробуйте нажать кнопку в главном меню или отправить запрос на какой-либо срез данных, например: 'Покажи грузооборот за февраль по неделям'")

	send_chart(message, query)

@bot.message_handler(content_types=['audio', 'voice'])
def voice_handler(message):
	model = "whisper-1"

	try:
		file_info = bot.get_file(message.audio.file_id)
	except:
		file_info = bot.get_file(message.voice.file_id)
	audio_file = bot.download_file(file_info.file_path)
	audio_file = io.BytesIO(audio_file)

	audio_file.name = 'sound.mp3'

	transcript = openai_client.audio.transcriptions.create(
		model=model, 
		file=audio_file
	)

	query = transcript.text

	send_chart(message, query)

while True:
	try:
		bot.polling()
	except:
		traceback.print_exc()
		time.sleep(5)


