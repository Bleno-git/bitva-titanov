from api import *

def upload():
	def load_csv(file_path="", data={}, prefix=""):
		with open(file_path, newline='') as csvfile:
			reader = csv.DictReader(csvfile)
			for row in reader:
				request_id = int(row['request_number'])
				del row['request_number']
				if request_id not in data:
					data[request_id] = {}
				if prefix == 'cost_price':
					data[request_id][prefix] = data[request_id].get(prefix, []) + [row]
				else:
					data[request_id].update({prefix: dict(row)})
		return data

	data = {}
	data = load_csv("raw/cost_data.csv", data, "cost_price")
	data = load_csv("raw/shipping_data_fact.csv", data, "fact")
	data = load_csv("raw/shipping_data_plan.csv", data, "plan")

	locations = {(region, name): ID for region, name, ID in execute_sql("SELECT region, name, id FROM locations")}

	to_insert = []
	to_insert_cost_data = []

	done = 0
	total = 0
	for i, request_id in enumerate(data):
		total += 1
		is_completed = 0

		if 'plan' in data[request_id]:
			name = data[request_id]['plan']['storage_loading_name'].strip().strip('.')
			region = data[request_id]['plan']['storage_loading_name_region'].strip().strip('.')

			if (region, name) not in locations:
				loc_id = execute_sql("INSERT INTO locations(region, name) values(%s, %s)", region, name, show_id=True)
				locations[(region, name)] = loc_id

			loading_loc_id = locations[(region, name)]

			name = data[request_id]['plan']['storage_unloading_name'].strip().strip('.')
			region = data[request_id]['plan']['storage_unloading_name_region'].strip().strip('.')

			if (region, name) not in locations:
				loc_id = execute_sql("INSERT INTO locations(region, name) values(%s, %s)", region, name, show_id=True)
				locations[(region, name)] = loc_id

			unloading_loc_id = locations[(region, name)]

		for group in ["fact", "plan"]:
			if group in data[request_id]:
				for key in data[request_id][group]:
					data[request_id][group][key] = data[request_id][group][key].lower()
					try:
						data[request_id][group][key] = float(data[request_id][group][key])
					except:
						pass
					is_completed = 1

		if "plan" in data[request_id]:
			load_time = unix_from_date(data[request_id]["plan"]["date_loading_planned"])
		else:
			load_time = 0

		if "fact" in data[request_id]:
			unload_time = unix_from_date(data[request_id]["fact"]["date_unloading"])
		else:
			unload_time = 0


		if "cost_price" in data[request_id]:
			for item in data[request_id]["cost_price"]:
				cost_name = item["cost_name"]
				cost_price_value = float(item["value"])

				to_insert_cost_data.append([request_id, cost_name, cost_price_value])

			revenue = data[request_id]["plan"]["price"]
			fact_volume = data[request_id]["fact"]["volume_unloaded"]

			cargo_type = data[request_id]["plan"]["commodity_name"]
			done += 1
		else:
			fact_volume = 0

		to_insert.append([request_id, 1, loading_loc_id, unloading_loc_id, revenue, fact_volume, load_time, unload_time, cargo_type])

	sql = SQL(mysql_host, mysql_user, mysql_password, mysql_db)

	q = "INSERT IGNORE INTO archive(request_id, is_completed, from_loc_id, to_loc_id, revenue, fact_volume, load_time, unload_time, cargo_type) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)"
	for i, chunk in enumerate(chunks(to_insert, 200)):
		sql.cursor.executemany(q, list(chunk))
		sql.conn.commit()

	q = "INSERT IGNORE INTO cost_data(request_id, cost_type, cost_amount) VALUES(%s, %s, %s)"
	for i, chunk in enumerate(chunks(to_insert_cost_data, 200)):
		sql.cursor.executemany(q, list(chunk))
		sql.conn.commit()

	sql.close()

	return {
		"not_delivered" : done,
		"total" : total
	}

def recalculate():
	to_insert = []
	for req_id, total_costs in execute_sql("SELECT request_id, sum(cost_amount) from cost_data group by request_id;"):
		to_insert.append([req_id, total_costs])

	to_insert_fact_finances = []
	for unload_day, total_revenue, total_count, total_costs, total_volume, total_profit in execute_sql("SELECT unload_time div 86400 * 86400, sum(revenue*fact_volume), count(*), sum(total_costs), sum(fact_volume), sum(revenue*fact_volume)-sum(total_costs) from archive group by unload_time div 86400 * 86400"):
		to_insert_fact_finances.append([unload_day, total_revenue, total_count, total_costs, total_volume, total_profit])

	fact_finances_cargo_type = []
	for unload_day, cargo_type, total_revenue, total_count, total_costs, total_volume, total_profit in execute_sql("SELECT unload_time div 86400 * 86400, cargo_type, sum(revenue*fact_volume), count(*), sum(total_costs), sum(fact_volume), sum(revenue*fact_volume)-sum(total_costs) from archive group by unload_time div 86400 * 86400, cargo_type"):
		fact_finances_cargo_type.append([unload_day, cargo_type, total_revenue, total_count, total_costs, total_volume, total_profit])

	fact_finances_locations = []
	for unload_day, to_loc_id, total_revenue, total_count, total_costs, total_volume, total_profit in execute_sql("SELECT unload_time div 86400 * 86400, to_loc_id, sum(revenue*fact_volume), count(*), sum(total_costs), sum(fact_volume), sum(revenue*fact_volume)-sum(total_costs) from archive group by unload_time div 86400 * 86400, to_loc_id"):
		fact_finances_locations.append([unload_day, to_loc_id, total_revenue, total_count, total_costs, total_volume, total_profit])

	sql = SQL(mysql_host, mysql_user, mysql_password, mysql_db)

	# Пересчитываем общие расходы и добавляем в индексируемые колонки для быстрого доступа
	q = "INSERT IGNORE INTO archive(request_id, total_costs) VALUES(%s, %s) ON DUPLICATE KEY UPDATE total_costs=values(total_costs)"
	for i, chunk in enumerate(chunks(to_insert, 200)):
		sql.cursor.executemany(q, list(chunk))
		sql.conn.commit()

	# Считаем выручку, общее кол-во перевозок, общие расходы по дням
	q = "INSERT IGNORE INTO fact_finances(unload_day, total_revenue, total_count, total_costs, total_volume, total_profit) VALUES(%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE total_revenue=values(total_revenue), total_count=values(total_count), total_costs=values(total_costs), total_volume=values(total_volume), total_profit=values(total_profit)"
	for i, chunk in enumerate(chunks(to_insert_fact_finances, 200)):
		sql.cursor.executemany(q, list(chunk))
		sql.conn.commit()

	# Считаем выручку, общее кол-во перевозок, общие расходы по культурам и дням
	q = "INSERT IGNORE INTO fact_finances_cargo_type(unload_day, cargo_type, total_revenue, total_count, total_costs, total_volume, total_profit) VALUES(%s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE total_revenue=values(total_revenue), total_count=values(total_count), total_costs=values(total_costs), total_volume=values(total_volume), total_profit=values(total_profit)"
	for i, chunk in enumerate(chunks(fact_finances_cargo_type, 200)):
		sql.cursor.executemany(q, list(chunk))
		sql.conn.commit()

	# Считаем выручку, общее кол-во перевозок, общие расходы по регионам (городу) и дням
	q = "INSERT IGNORE INTO fact_finances_locations(unload_day, location_id, total_revenue, total_count, total_costs, total_volume, total_profit) VALUES(%s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE total_revenue=values(total_revenue), total_count=values(total_count), total_costs=values(total_costs), total_volume=values(total_volume), total_profit=values(total_profit)"
	for i, chunk in enumerate(chunks(fact_finances_locations, 200)):
		sql.cursor.executemany(q, list(chunk))
		sql.conn.commit()

	sql.close()

def process_user_request(text):
	messages = [
	{"role" : "user", "content": """Ты - API, которое по сообщению пользователя определяет из какой таблицы базы данных нужно достать данные для отображения в виде графика.
	Твоя задача определить:
	1) Таблицу с данными
	2) Нужную колонку
	3) Дату получения данных от и до
	4) Заголовок для графика, который описывает данные
	5) За какой период сгруппированны данные. Если пользователь явно не указал, то используется группировка по дням. Возможные варианты: "day", "week", "month"

	Возможные таблицы и колонки в них (в ключе словаря - таблица, в значении - название колонки и её описание, в ключи table_desc - описание таблицы):
	{
		"fact_finances" : {
			"table_desc" : "В этой таблице хранится срез данных по выручке, расходам, прибыли и количеству грузоперевозок сгруппированные по дням",
			"columns" : [["total_revenue", "Выручка за день"], ["total_count", "Общее количество грузоперевозок за день"], ["total_costs", "Расходы на транспортирку за день"], ["total_volume", "Общий объём грузоперевозок за день в тоннах"], ["total_profit", "Прибыль за день"]]
		},
		"fact_finances_cargo_type" : {
			"table_desc" : "В этой таблице хранится срез данных по выручке, расходам, прибыли и количеству грузоперевозок сгруппированные по дням и культурам",
			"columns" : [["total_revenue", "Выручка за день"], ["total_count", "Общее количество грузоперевозок за день"], ["total_costs", "Расходы на транспортирку за день"], ["total_volume", "Общий объём грузоперевозок за день в тоннах"], ["total_profit", "Прибыль за день"]]
		},
		"fact_finances_locations" : {
			"table_desc" : "В этой таблице хранится срез данных по выручке, расходам, прибыли и количеству грузоперевозок сгруппированные по дням и локациям, где происходила выгрузка",
			"columns" : [["location_id", "ID локации, где был выгружен груз"], ["total_count", "Общее количество грузоперевозок за день"], ["total_costs", "Расходы на транспортирку за день"], ["total_volume", "Общий объём грузоперевозок за день в тоннах"], ["total_profit", "Прибыль за день"]]
		},
	}

	Структура твоего ответа должна быть в виде массива, в котором хранятся словари, пример:
	[{"table": "fact_finances", "column": "total_revenue", "date_from": "20-03-2024", "date_to": "21-03-2024", "title" : "Выручка за 20 марта", "group" : "day"}]

	Пример вопроса пользователя: "Динамика перевозок за март. Сегодня 19.04.2024"
	Твой ответ должен быть:
	[{"table": "fact_finances", "column": "total_count", "date_from": "01-03-2024", "date_to": "31-03-2024", "title" : "Динамика перевозок за март", "group" : "day"}]

	Другой пример вопроса пользователя: "Выручка за январь по неделям. Сегодня 19.04.2024"
	Твой ответ должен быть:
	[{"table": "fact_finances", "column": "total_count", "date_from": "01-01-2024", "date_to": "31-01-2024", "title" : "Выручка за январь", "group" : "week"}]

	Между датами, которые ты возвращаешь, должен быть минимум один день. Не отправляй одинаковые даты.
	Даты в ответе возвращай в формате "год-месяц-день"

	Данные начинаются с 2023 года

	В ответе верни только JSON и ничего больше. Не отправляй мне никакого форматирования
	"""},
		{"role" : "user", "content": text + '\n' + f'Сегодня {datetime.now().strftime("%d.%m.%Y")}'},
	]

	response = ask_ai(messages=messages).replace('```json', '').replace('```', '')

	return json.loads(response)

def extract_data(instructions):
	data = []
	for instruction in instructions:
		date_from = unix_from_date(instruction["date_from"])
		date_to = unix_from_date(instruction["date_to"])

		group = instruction['group']

		group_t = ""
		if group == 'day':
			group_t = ""
		if group == 'week':
			group_t = "group by unload_day div (86400*7)"
		if group == 'month':
			group_t = "group by month(FROM_UNIXTIME(unload_day))"

		execute_sql("SET GLOBAL sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''));")

		if group == "day":
			query = "SELECT unload_day, {column_name} FROM {table_name} WHERE unload_day >= %s AND unload_day <= %s {group} order by unload_day".format(column_name=instruction["column"], table_name=instruction["table"], group=group_t)
		else:
			query = "SELECT unload_day, sum({column_name}) FROM {table_name} WHERE unload_day >= %s AND unload_day <= %s {group} order by unload_day".format(column_name=instruction["column"], table_name=instruction["table"], group=group_t)
		# print(query, date_from, date_to)
		d = execute_sql(query, date_from, date_to)


		if group == "week":
			data.append([[unix_to_day(day), int(value)] for day, value in d])
		if group == "day":
			data.append([[unix_to_day(day), int(value)] for day, value in d])
		if group == "month":
			data.append([[unix_to_month(day), int(value)] for day, value in d])

	return data

def dashboard():
	total_revenue = execute_sql("SELECT sum(revenue) FROM archive")[0][0]
	total_costs = execute_sql("SELECT sum(cost_price_value) FROM archive")[0][0]
	total_profit = total_revenue - total_costs

	users_count = execute_sql("SELECT count(*) FROM users")[0][0]

	return {
		"total_revenue" : total_revenue,
		"total_costs" : total_costs,
		"total_profit" : total_profit,
		"tg_users_count" : users_count
	}

server = Flask(__name__)

@server.route("/chart/<query>")
def chart_view(query):
	try:
		d = datetime.now().strftime("%d.%m.%Y")
		query = query + f". Сегодня {d}"
		if not execute_sql("SELECT count(*) FROM ai_requests WHERE query=%s", query)[0][0]:
			instructions = process_user_request(query)
			execute_sql("INSERT INTO ai_requests(query, answer, time) values(%s, %s, unix_timestamp())", query, json.dumps(instructions))
		else:
			instructions = json.loads(execute_sql("SELECT answer FROM ai_requests WHERE query=%s", query)[0][0])

		charts = {}

		for i, item in enumerate(instructions):
			chart_title = instructions[0]['title']
			date_from = instructions[0]['date_from']
			date_to = instructions[0]['date_to']

			data_for_chart = extract_data(instructions)[0]

			chart_titles = [item[0] for item in data_for_chart]
			chart_values = [convert_number(item[1]) for item in data_for_chart]

			charts[i] = {
				"chart_title": chart_title,
				"date_from": date_from,
				"date_to": date_to,
				"data_for_chart": data_for_chart,
				"chart_titles": chart_titles,
				"chart_values": chart_values
			}

		return render_template("chart.html", charts=charts)
	except:
		return "Не удалось получить срез. Попробуйте другой запрос"

@server.route("/dashboard/")
def dashboard_view():
	revenue_group = request.args.get("revenue")
	if revenue_group not in ["day", "week", "month"]:
		revenue_group = "day"
	revenue_group = "month"


	instructions = [
		{"table": "fact_finances", "column": "total_revenue", "date_from": "2023-01-01", "date_to": "2024-12-01", "title": "Динамика выручки по месяцам", "group": revenue_group},
		{"table": "fact_finances", "column": "total_volume", "date_from": "2023-01-01", "date_to": "2024-12-01", "title": "Динамика грузоперевозок по месяцам", "group": revenue_group},
	]
	charts = {}
	for i, instruction in enumerate(instructions):
		data_for_chart = extract_data([instruction])[0]
		chart_title = instruction['title']
		date_from = instruction['date_from']
		date_to = instruction['date_to']

		chart_titles = [item[0] for item in data_for_chart]
		chart_values = [convert_number(item[1]) for item in data_for_chart]

		charts[i] = {
			"chart_title": chart_title,
			"date_from": date_from,
			"date_to": date_to,
			"data_for_chart": data_for_chart,
			"chart_titles": chart_titles,
			"chart_values": chart_values
		}



	cargo_chart_data = [[cargo_type.capitalize(), revenue] for cargo_type, revenue in execute_sql("SELECT cargo_type, sum(revenue) FROM archive group by cargo_type")]
	cargo_types = [item[0] for item in cargo_chart_data]

	cargo_chart_data = [{"value" : value, "name" : name} for name, value in cargo_chart_data]

	month_start = time.mktime(datetime(month=int(datetime.now().strftime('%m')), year=int(datetime.now().strftime('%Y')), day=1).timetuple())

	revenue_soya_this_month = str(round(execute_sql("SELECT sum(total_revenue) / 1000000 from fact_finances_cargo_type where unload_day > %s and cargo_type='соя';", month_start)[0][0], 2)).replace('.', ',')
	revenue_kukuruza_this_month = str(round(execute_sql("SELECT sum(total_revenue) / 1000000 from fact_finances_cargo_type where unload_day > %s and cargo_type='кукуруза';", month_start)[0][0], 2)).replace('.', ',')
	revenue_yachmen_this_month = str(round(execute_sql("SELECT sum(total_revenue) / 1000000 from fact_finances_cargo_type where unload_day > %s and cargo_type='ячмень';", month_start)[0][0], 2)).replace('.', ',')

	print(charts)


	return render_template("dashboard.html", charts=charts, cargo_types=cargo_types, cargo_chart_data=cargo_chart_data, revenue_soya_this_month=revenue_soya_this_month, revenue_kukuruza_this_month=revenue_kukuruza_this_month, revenue_yachmen_this_month=revenue_yachmen_this_month)

@server.route("/api/")
@server.route("/api/docs/")
@server.route("/api/help/")
def about_view():
	return render_template("documentation.html")

@server.route("/api/version/")
@server.route("/api/version")
def version_view():
	if check_api_tokens(request)["priority"] < 999:
		abort(403)
	return jsonify({
		"version": "1.0.0",
		"description": "Данная версия используется как MVP бота для аналитики"
	})


@server.route("/api/upload/<file_name>")
def upload_view(file_name, methods=["POST"]):
	if check_api_tokens(request)["priority"] < 999:
		abort(403)

	if file_name not in ['cost_data', 'shipping_data_fact', 'shipping_data_plan']:
		return jsonify({"status" : "err", "msg" : "Доступные данные для загрузки: ['cost_data', 'shipping_data_fact', 'shipping_data_plan']"})

	request.files.get(file_name).save(f"raw/{file_name}.csv")

	return jsonify({
		"status" : "ok",
		"msg" : "Файл успешно загружен в базу данных"
	})

@server.route("/api/dashboard/")
def get_dashboard_view(methods=["GET"]):
	if check_api_tokens(request)["priority"] < 999:
		abort(403)

	users_count = execute_sql("SELECT count(*) FROM users")[0][0]
	return jsonify({
		"status" : "ok",
		"data" : dashboard()
	})

@server.errorhandler(404)
def error_404(e):
	return redirect('/dashboard')


server.run(debug=True, port=8080, host="0.0.0.0")

