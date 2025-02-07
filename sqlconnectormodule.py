
from decimal import Decimal
import pymysql
import logging

# Configure logging (optional, but good practice)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SQL:
	"""
	A class for managing MySQL database connections and queries.
	Handles connection pooling, query execution, and data formatting.
	"""

	def __init__(self, host, login, password, db_name, get_pid=False):
		"""
		Initializes a new SQL connection.
		"""
		self.pid = None  # Process ID for potential connection termination
		self._db_config = {'host': host, 'user': login, 'password': password, 'db': db_name} # Store connection details
		self._conn = self._create_connection()  # Create connection immediately
		self._cursor = self._conn.cursor() # Buffered cursor for iterating result set
		if get_pid:
			self.pid = self.run("SELECT connection_id();")[0][0]
		logging.info(f"Connected to database: {db_name} on {host}")

	def _create_connection(self):
		"""
		Establishes a connection to the MySQL database.
		"""
		try:
			conn = pymysql.connect(**self._db_config)
			conn.autocommit = False  # Disable autocommit for transaction control
			return conn
		except pymysql.MySQLError as e:
			logging.error(f"Error connecting to database: {e}")
			raise

	def kill_me(self):
		"""
		Kills the current database connection (if PID is available).
		"""
		if self.pid:
			self.run(f"KILL {self.pid}")
			logging.info(f"Killed connection with PID: {self.pid}")
		self.close()

	def execute(self, query, params=None, show=True):
		"""
		Executes a SQL query. Supports parameterized queries and returns results if show is True.
		"""
		try:
			if params:
				self._cursor.execute(query, params)
			else:
				self._cursor.execute(query)

			if show:
				results = self._fetch_and_format_results()
				self._conn.commit() # Commit the transaction if successful
				return results
			else:
				self._conn.commit() # Still commit even if not returning results
				return None

		except pymysql.MySQLError as e:
			self._conn.rollback() # Rollback in case of error
			logging.error(f"SQL execution error: {e}")
			raise  # Re-raise the exception

	def _fetch_and_format_results(self):
		"""
		Fetches all results from the cursor and formats Decimal values to floats.
		"""
		results = []
		for row in self._cursor:
			row = list(row)
			for i in range(len(row)):
				if isinstance(row[i], Decimal):
					row[i] = float(row[i])
			results.append(row)
		return results

	def json(self, query, *params):
		"""
		Executes a SQL query and returns the results as a list of dictionaries.
		Converts Decimal values to floats.
		"""
		try:
			self._cursor.execute(query, params)
			try:
				column_names = [desc[0] for desc in self._cursor.description]
			except:
				column_names = []  # Handle case where there are no results

			results = []
			for row in self._cursor:
				row = list(row)
				for i in range(len(row)):
					if isinstance(row[i], Decimal):
						row[i] = float(row[i])
				results.append(dict(zip(column_names, row)))

			self.commit()
			return results

		except pymysql.MySQLError as e:
			self.commit()
			logging.error(f"SQL execution error for JSON: {e}")
			raise

	def run(self, query, *params):
		"""
		Executes a SQL query and returns the results as a list of tuples.
		Converts Decimal values to floats.
		"""
		try:
			self._cursor.execute(query, params)
			results = self._fetch_and_format_results()
			self.commit()  # Commit transaction after successful execution
			return results
		except pymysql.MySQLError as e:
			self.rollback() # Rollback on error
			logging.error(f"SQL execution error: {e}")
			raise  # Re-raise the exception

	def commit(self):
		"""
		Commits the current transaction.
		"""
		try:
			self._conn.commit()
		except pymysql.MySQLError as e:
			logging.error(f"Error committing transaction: {e}")
			raise

	def rollback(self):
	   """
	   Rolls back the current transaction
	   """
	   try:
			self._conn.rollback()
	   except pymysql.MySQLError as e:
			logging.error(f"Error rollback transaction: {e}")
			raise

	def reset(self):
		"""
		Resets the cursor by creating a new one.
		"""
		try:
			self._cursor.close()
			self._cursor = self._conn.cursor()
			logging.info("Cursor reset successfully.")
		except pymysql.MySQLError as e:
			logging.error(f"Error resetting cursor: {e}")
			raise

	def close(self):
		"""
		Closes the cursor and the database connection.
		"""
		try:
			self._cursor.close()
			self._conn.close()
			logging.info("Connection closed successfully.")
		except pymysql.MySQLError as e:
			logging.error(f"Error closing connection: {e}")
			raise

