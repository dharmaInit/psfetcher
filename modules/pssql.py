from more_itertools import unique_everseen
import sqlite3

from modules.globals import MINPRICE, MAXPRICE


def maketables(dbfile=None):
	"""Return None. Create psfetcher's 2 main tables.

	First table, 'psfetcher', stores all fetched information.
	Second table, 'watchlist', stores all added titles from the 'watchlist' command.

	Parameters:
	dbfile (str): full path to a database file
	"""
	maindb = """
	create table if not exists psfetcher
	(id integer primary key autoincrement,
	titleID blob, title blob, price blob,
	discount blob, roundprice real, type blob,
	deal blob, pagenumber integer, dealID blob,
	locale text, platform blob)
	"""
	watchdb = """
	create table if not exists watchlist
	(id integer primary key autoincrement,
	title blob, titleID, locale blob)
	"""
	c = sqlite3.connect(dbfile)
	[c.cursor().execute(statement) for statement in (maindb, watchdb)]
	c.commit()
	c.close()


def cleanup(dbfile=None, deal=None, dealID=None, locale=None):
	"""Return None. Remove all fetched items of a deal.

	Parameters:
	dbfile (str): full path to a database file
	deal (str): deal's name
	dealID (str): deal's ID
	locale (str): language and country codes joined with a hyphen
	"""
	c = sqlite3.connect(dbfile)
	statement = "delete from psfetcher where dealID = ? and locale = ? and deal = ?"
	c.cursor().execute(statement, (dealID, locale, deal))
	c.commit()
	c.close()


def flush(dbfile=None, everything=False):
	"""Return None. Remove all items from the table 'psfetcher'.

	Parameters:
	dbfile (str): full path to a database file
	everything (bool): if True, will also remove all items from the 'watchlist' table.
	"""
	c = sqlite3.connect(dbfile)
	try:
		c.cursor().execute("delete from psfetcher")
		if everything:
			c.cursor().execute("delete from watchlist")
		c.commit()
	except sqlite3.OperationalError:
		pass
	c.close()


def oldcount(dbfile=None, deal=None, dealID=None, locale=None):
	"""Return total count of items and total count of pages from the previous run.

	In case of a clean database, '0, 0' is returned.

	Parameters:
	dbfile (str): full path to a database file
	deal (str): deal's name
	dealID (str): deal's ID
	locale (str): language and country codes joined with a hyphen
	"""
	c = sqlite3.connect(dbfile)
	try:
		statement = "select count(title) from psfetcher where dealID = ? and locale = ? and deal = ?"
		oldcount, = c.execute(statement, (dealID, locale, deal)).fetchone()
		if oldcount > 0:
			statement = "select max(pagenumber) from psfetcher where dealID = ? and locale = ? and deal = ?"
			totalpages, = c.execute(statement, (dealID, locale, deal)).fetchone()
			return oldcount, totalpages
		return 0, 0
	except sqlite3.OperationalError:
		return 0, 0
	c.close()


def mainselect(
	dbfile=None, deal=None, dealID=None, locale=None,
	lang=None, country=None, minprice=0, maxprice=0,
	sortingList=None, reverseResults=False, allcontent=None, contentTypes=None
):
	"""Return itemlist, maximum title length, maximum price length, and a message of applied filters.

	In case of a TypeError, return None, 0, 0, None.

	Parameters:
	dbfile (str): full path to a database file
	deal (str): deal's name
	dealID (str): deal's ID
	locale (str): language and country codes joined with a hyphen
	lang (str): 2-letter language code
	country (str): 2-letter country code
	minpirce (int): title's minimum price
	maxprice (int): title's maximum price
	sortingList (list): a list of user-applied sorting
	reverseResults (bool): if True, will reverse the order of user-applied sorting
	allcontent (dict): second dict, allcontent, returned from psconfig.getConf
	contentTypes (list): a list of user-picked content types
	"""
	# messages for applied filters
	contentMes = priceRangeMes = sortMes = ""

	if minprice != MINPRICE:
		priceRangeMes += "from {} ".format(minprice)
	if maxprice != MAXPRICE:
		priceRangeMes += "under {}".format(maxprice)
	if priceRangeMes:
		priceRangeMes = "price range: " + priceRangeMes

	select = """
	select title, price, discount, titleID, id, platform from psfetcher
	where roundprice between {} and {}
	and dealID = '{}' and locale = '{}' and deal = '{}'
	""".format(minprice, maxprice, dealID, locale, deal)

	if contentTypes:
		ctypes = []
		for ctype in contentTypes:
			ctypes += allcontent[lang][ctype]
		placeholders = "?" * len(ctypes)
		placeholders = ",".join(placeholders)
		select += " and psfetcher.type in ({})".format(placeholders)
		contentMes = "content: {}".format(", ".join(contentTypes))

	if sortingList:
		sortingList = list(unique_everseen(sortingList))
		sortingListSQL = ["roundprice" if i == "price" else i for i in sortingList]
		order = {False: " asc", True: " desc"}
		order = order[reverseResults]
		select += " order by " + "{}, ".format(order).join(sortingListSQL) + order
		sortMes = "sorted by {}".format(" then by ".join(sortingList))
		if reverseResults:
			sortMes += " in reverse"

	try:
		c = sqlite3.connect(dbfile)
		titleSelect = """
		select length(title) from psfetcher
		where dealID = ? and locale = ? and deal = ?
		order by length(title) desc limit 1
		"""
		maxTitleLen, = c.execute(titleSelect, (dealID, locale, deal)).fetchone()

		priceSelect = """
		select length(price) from psfetcher
		where dealID = ? and locale = ? and deal = ?
		order by length(price) desc limit 1
		"""
		maxPriceLen, = c.execute(priceSelect, (dealID, locale, deal)).fetchone()

		itemlist = []
		if contentTypes:
			select = c.cursor().execute(select, ctypes)
		else:
			select = c.cursor().execute(select)
		for title, price, discount, titleID, ind, platform in select.fetchall():
			rawdata = {}
			rawdata["title"] = title
			rawdata["price"] = price
			rawdata["discount"] = discount
			rawdata["titleID"] = titleID
			rawdata["id"] = ind
			rawdata["platform"] = platform
			itemlist.append(rawdata)
		c.close()

		filterMessage = "{} titles".format(len(itemlist))
		messages = [m for m in (sortMes, priceRangeMes, contentMes) if m]
		for message in messages:
			filterMessage += " | {}".format(message)
		return itemlist, maxTitleLen, maxPriceLen, filterMessage

	except TypeError:
		return None, 0, 0, None
