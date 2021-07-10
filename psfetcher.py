from itertools import repeat
import bs4
import json
import multiprocessing
import re
import requests
import sqlite3
import sys

from modules import psconfig, psinfo, psparse, pssql
from modules.globals import DBFILE


def webparser(url):
	"""Return a BeautifulSoup soup object for a given URL.

	A Playstation Store base URL is added to the passed URL if it's local.
	"""
	if not url.startswith("https"):
		url = "https://store.playstation.com" + url
	res = requests.get(url)
	assert res.status_code == 200, "can't reach {}".format(url)
	soup = bs4.BeautifulSoup(res.text, "lxml")
	return soup


def choiceCheck(maxval, attempt=1, inputMessage="enter deal's index: "):
	"""Return a list of unique, positive integers from input.

	Each integer must be less than or equal to maxval.
	Return None after (by default) 3 failed attempts (when input is greater than maxval).

	Parameters:
	maxval (int): maximum integer value
	attempt (int): attempt number
	inputMessage (str): input message
	"""
	messagePool = ["wait, that's illegal!", "believe in yourself", "heh, okay."]
	choices = list(set(input(inputMessage).split()))
	choices = [int(c) for c in choices if c.isdigit() and 0 < int(c) <= maxval]
	if choices == []:
		if attempt >= 3:
			print(messagePool[-1])
			return None
		print(messagePool[attempt-1])
		choices = choiceCheck(maxval, attempt=attempt+1, inputMessage=inputMessage)
	return choices


def getdeals(lang, country, fetchall=False):
	"""Return a list of tuples. Each tuple consists of a deal name and its local URL.

	Parameters:
	lang (str): 2-letter language code
	country (str): 2-letter country code
	fetchall (bool): if True, will get all current deals instead of chosen ones
	"""

	def footerDeal(name=None, soup=None):
		footerDealSoup = soup.select(".ems-sdk-strand__header")[0]
		if not name:
			name = footerDealSoup.text.lower()
		url = footerDealSoup.a.get("href").strip("1")
		return name, url

	def sanitiseDeal(name=None, url=None):
		if "product" in url:
			print("skipping a single item deal '{}'".format(name))
			return None, None

		# a deal url within a deal url
		dCeption = ["- web", "- wm"]
		for level in dCeption:
			if name.endswith(level):
				name = name.replace(level, "").strip()
				return name, "footer"

		return name, None

	mainpage = "https://store.playstation.com/{}-{}/deals".format(lang, country)
	soup = webparser(mainpage)
	storeDeals = soup.select("div .ems-sdk-collection")[0]
	deals = []
	if storeDeals:
		for deal in storeDeals.find_all("li"):
			name = deal.img.get("alt").replace("[PROMO] ", "").lower()
			url = deal.a.get("href").strip("1")
			name, placement = sanitiseDeal(name=name, url=url)
			if placement == "footer":
				name, url = footerDeal(name=name, soup=webparser(url))
			if name:
				deals.extend([(name, url)])

	# "all deals" deal
	name, url = footerDeal(soup=soup)
	deals.extend([(name, url)])

	if deals:
		if fetchall:
			print("fetching all deals:")
			[print(" *", i[0]) for i in deals]
		else:
			[print(ind + 1, deal[0]) for ind, deal in enumerate(deals)]
			choices = choiceCheck(maxval=len(deals))
			if not choices:
				return None
			deals = [deals[i-1] for i in choices]
		return deals


def itercount(dealurl):
	"""Return deal's total number of pages, items, and number of items per page.

	Parameters:
	dealurl (str): deal's local URL
	"""
	try:
		soup = webparser(dealurl + str(1))
		totalCountReg = re.compile(r"(\"totalCount\"):(\d+),(\"offset\"):(\d+),(\"size\"):(\d+)")
		regResults = totalCountReg.search(soup.prettify())
		totalCount = int(regResults.group(2))
		pageSize = int(regResults.group(6))
		if totalCount <= pageSize:
			totalPages = 1
		elif totalCount > pageSize:
			# round up
			totalPages = -(-totalCount // pageSize)
		return totalCount, totalPages, pageSize
	except (IndexError, AttributeError):
		return None, None, None


def itemPrice(dbfile=None, titleID=None, locale=None, deal=None, dealID=None):
	"""Return None. Fetch and write results to a SQL database.

	Fetches a single item's information by its ID.

	Parameters:
	dbfile (str): full path to a database file
	titleID (str): title's ID from PS Store
	locale (str): language and country codes joined with a hyphen
	deal (str): deal's name
	dealID (str): deal's ID
	"""
	url = "https://store.playstation.com/{}/product/{}".format(locale, titleID)
	soup = webparser(url)
	rawdata = soup.select("script", id="mfe-jsonld-tags", type="application/ld+json")
	jsonData = json.loads(rawdata[11].string)["cache"]
	jsonKeys = list(jsonData.keys())
	matchIDReg = re.compile(r"GameCTA\S+{}".format(titleID))
	matchID = matchIDReg.search(" ".join(jsonKeys)).group(0)
	titleStoreID = [k for k in jsonKeys if matchID in k][0]
	priceJson = jsonData[titleStoreID]["price"]
	try:
		noCurrencyReg = re.compile(r"[0-9,.\s]+")
		price = noCurrencyReg.search(priceJson["discountedPrice"]).group()
		price = price.translate(str.maketrans({" ": None, ",": "."}))
		decSepPosition = price.find(".") + 1
		if len(price[decSepPosition:]) >= 3:
			price = price.replace(".", "")
	except (AttributeError, TypeError):
		price = 0.1

	platformKey = "Product:{}".format(titleID)
	platform = json.loads(rawdata[10].string)["cache"][platformKey]["platforms"]
	platform = ", ".join(platform)
	if "PS" not in platform:
		platform = "PS*"

	roundPrice = round(float(price), 2)
	price = str(priceJson["discountedPrice"])
	discount = priceJson["discountText"]
	category = json.loads(rawdata[8].string)["category"]
	title = json.loads(rawdata[8].string)["name"]

	connection = sqlite3.connect(dbfile)
	statement = """
	insert into psfetcher
	(titleID, title, price, roundprice, discount,
	type, deal, pagenumber, dealID, locale, platform)
	values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	"""
	connection.cursor().execute(statement, (
		titleID, title, price, roundPrice, str(discount),
		category, deal, 1, dealID, locale, platform
		)
	)
	connection.commit()
	connection.close()


def getitems(
	dealurl=None, deal=None, pagenumber=None,
	pagesize=0, query=None, lang=None, country=None, dbfile=None
):
	"""Return None. Fetch and write results to a SQL database.

	Fetches information for all items per 1 page.

	Parameters:
	dealurl (str): deal's local URL
	deal (str): deal's name
	pagenumber (int): deal's page number
	pagesize (int): number of items per page
	query (str): search phrase
	lang (str): 2-letter language code
	country (str): 2-letter country code
	dbfile (str): full path to a database file
	"""

	sys.stderr.write("\033[K" + "page {}".format(pagenumber) + "\r")
	sys.stderr.flush()

	if dealurl:
		soup = webparser(dealurl + str(pagenumber))
	elif query:
		url = "https://store.playstation.com/{}-{}/search/{}"
		url = url.format(lang, country, query.replace(" ", "%20"))
		soup = webparser(url)

	dataDump = json.loads(soup.find("script", id="__NEXT_DATA__").string)
	productIDTree = dataDump["props"]["apolloState"]

	productIDs = []
	if dealurl:
		# unique child 'CategoryGrid' for json tree:
		# a deal id + lang + country + total number of items already shown
		dealID = dealurl.split("/")[-2]
		continueFrom = 0
		if pagenumber > 1:
			continueFrom = pagenumber * pagesize - pagesize
		categoryJs = "CategoryGrid:{}:{}-{}:{}:{}".format(
			dealID, lang, country, continueFrom, pagesize
		)
		for i in productIDTree[categoryJs]["products"]:
			productIDs.append(i["id"])
	elif query:
		dealID = query
		for productID in productIDTree:
			locale = ":{}-{}".format(lang, country)
			if productID.startswith("Product") and \
				(productID.endswith(locale) or productID.endswith(":en-us")):
				productIDs.append(productID)

	locale = lang + "-" + country
	noCurrencyReg = re.compile(r"[0-9,.\s]+")
	connection = sqlite3.connect(dbfile)
	c = connection.cursor()
	for productID in productIDs:
		itemInfo = dataDump["props"]["apolloState"][productID]
		if query:
			if not query.lower() in itemInfo["name"].lower():
				continue

		priceID = itemInfo["price"]["id"]
		priceJson = dataDump["props"]["apolloState"][priceID]
		try:
			price = noCurrencyReg.search(priceJson["discountedPrice"]).group()
			price = price.translate(str.maketrans({" ": None, ",": "."}))
			# fix decimal separator rounding issue: if len after dec. sep. position is >= 3
			decSepPosition = price.find(".") + 1
			if len(price[decSepPosition:]) >= 3:
				price = price.replace(".", "")
			roundPrice = round(float(price), 2)
		except (KeyError, AttributeError, ValueError):
			roundPrice = 0.1

		platform = ", ".join(itemInfo["platforms"]["json"])
		if "PS" not in platform:
			platform = "PS*"

		statement = """
		insert into psfetcher
		(titleID, title, price, roundprice, discount,
		type, deal, pagenumber, dealID, locale, platform)
		values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		"""
		c.execute(statement, (
			itemInfo["id"], itemInfo["name"].strip(),
			priceJson["discountedPrice"], roundPrice,
			str(priceJson["discountText"]),
			itemInfo["localizedStoreDisplayClassification"], deal, pagenumber, dealID, locale, platform
			)
		)
	connection.commit()
	connection.close()


def printitems(itemlist, tlen=0, plen=0, table=False):
	"""Return None. Print formatted results from itemlist.

	Parameters:
	itemlist (list): data list of items (dicts)
	tlen (int): title length value used for justification
	plen (int): price length value used for justification
	table (bool): if True, will print table-like results
	"""
	header = "{} | {} | {} | {}".format(
		"Title".ljust(tlen), "Price".ljust(plen),
		"Discount", "Platform"
	)
	dlen = len("Discount")
	print(header)
	for item in itemlist:
		if table:
			print("-" * round(len(header)))
		itemline = "{} | {} | {} | {}".format(
			item["title"].ljust(tlen),
			item["price"].ljust(plen),
			str(item["discount"]).ljust(dlen),
			str(item["platform"]))
		print(itemline)


def watchlist(dbfile=None, locale=None, command=None, addtitle=None):
	"""Return None.

	Based on an option, either show titles, add a title, check prices or remove a title.

	dbfile (str): full path to a database file
	locale (str): language and country codes joined with a hyphen
	command (str): command to execute (add, check, show, remove)
	addtitle (str): search and add a title to the watchlist db
	"""
	connection = sqlite3.connect(dbfile)
	c = connection.cursor()
	totalCount, = c.execute("select count(titleID) from watchlist").fetchone()
	if command == "show" and totalCount != 0:
		statement = "select length(title) from watchlist order by length(title) desc limit 1"
		maxTitleLen, = c.execute(statement).fetchone()
		print("Title".ljust(maxTitleLen), "Store")
		for title, locale in c.execute("select title, locale from watchlist").fetchall():
			print(title.ljust(maxTitleLen), locale)

	elif command == "check" and totalCount != 0:
		titleIDs = []
		locales = []
		statement = "select titleID, locale from watchlist where locale = ?"
		for titleID, locale in c.execute(statement, (locale,)).fetchall():
			titleIDs.append(titleID)
			locales.append(locale)
		p = multiprocessing.Pool(processes=multiprocessing.cpu_count())
		p.starmap(itemPrice, zip(
			repeat(dbfile), titleIDs, locales,
			repeat("watchlist"), repeat("watchlist")
			)
		)
		p.close()
		p.join()

	elif command == "add" and addtitle:
		c.execute("delete from psfetcher where deal = 'watchlist'")
		c.execute("update sqlite_sequence set seq=0 where name='psfetcher'")
		connection.commit()

		lang, country = locale.split("-")
		getitems(query=addtitle, deal="watchlist", lang=lang, country=country, pagenumber=1, dbfile=dbfile)

		indexConverter = {}
		statement = "select id, title from psfetcher where deal = 'watchlist'"
		watchQueryResults = c.execute(statement).fetchall()
		if not watchQueryResults:
			return None
		for ind, IDWithTitle in enumerate(watchQueryResults, start=1):
			ID = IDWithTitle[0]
			title = IDWithTitle[1]
			print(ind, title)
			indexConverter[ind] = ID
		del watchQueryResults
		choices = choiceCheck(maxval=len(indexConverter), attempt=1, inputMessage="enter title's index: ")
		if not choices:
			return None
		# revert back from enumerated indexes to the real ids in the table
		finalIDs = [str(indexConverter[ind]) for ind in choices]
		placeholders = "?" * len(finalIDs)
		placeholders = ",".join(finalIDs)
		statement = "select title, titleID from psfetcher where deal = 'watchlist' and id in ({})"
		for title, titleID in c.execute(statement.format(placeholders)).fetchall():
			statement = "select titleID from watchlist where titleID = ? and locale = ?"
			if not c.execute(statement, (titleID, locale)).fetchone():
				statement = "insert into watchlist (titleID, title, locale) values (?, ?, ?)"
				c.execute(statement, (titleID, title, locale))
		connection.commit()

	elif command == "remove" and totalCount != 0:
		for ind, ID, in enumerate(c.execute("select id from watchlist").fetchall(), start=1):
			c.execute("update watchlist set id = ? where id = ?", (ind, ID[0]))

		maxIDLen, = c.execute("select length(id) from watchlist order by length(id) desc limit 1").fetchone()
		if maxIDLen == 1:
			maxIDLen = 2
		maxTitleLen, = c.execute("select length(title) from watchlist order by length(title) desc limit 1").fetchone()
		print("ID".ljust(maxIDLen), "Title".ljust(maxTitleLen), "Store")
		for ID, title, locale in c.execute("select id, title, locale from watchlist"):
			print(str(ID).ljust(maxIDLen), title.ljust(maxTitleLen), locale)
		choices = choiceCheck(maxval=totalCount, attempt=1, inputMessage="enter title's index: ")
		if choices:
			for ind in choices:
				c.execute("delete from watchlist where id = ?", (ind,))
		c.execute("update sqlite_sequence set seq=0 where name='watchlist'")
		connection.commit()

	connection.close()


def listStores(conf=None):
	"""Return None. Print all possible language and country code combinations.

	Parameters:
	conf (dict): the first dict, allstores, returned from psconfig.getConf
	"""
	print("language", "|", "country")
	justVal = len("language")
	for lang, country in conf.items():
		line = "{} | {}".format(lang.ljust(justVal), " ".join(country))
		print(line)


def prelimCheck(
	country=None, lang=None, minprice=0, maxprice=0,
	conf=None, sortingList=None, contentTypes=None
):
	"""Return 1 if basic sanity check of arguments fails.

	Parameters:
	country (str): 2-letter country code
	lang (str): 2-letter language code
	minpirce (int): title's minimum price
	maxprice (int): title's maximum price
	conf (dict): the first dict, allstores, returned from psconfig.getConf
	sortingList (list): a list of user-applied sorting
	contentTypes (list): a list of user-picked content types
	"""
	if not lang:
		print("specify the language code")
		return 1
	if lang not in conf.keys():
		print("wrong language code specified")
		return 1
	if not country:
		print("specify the country code")
		return 1
	if country not in conf[lang]:
		print("wrong country and language code combination")
		return 1
	if 0 > minprice or minprice > maxprice:
		print("there there now, be a dear and fix those prices")
		return 1
	for level in sortingList:
		if level not in (["price", "title", "discount"]):
			print("wrong sorting is specified")
			return 1
	for level in contentTypes:
		if level not in (["game", "addon", "currency"]):
			print("wrong content is specified")
			return 1


def main():
	"""Psfetcher's main engine. Not meant to be imported."""

	# exit if the main config is not found
	allstores, allcontent = psconfig.getConf()
	if not allstores:
		sys.exit()

	# should a var be added/changed, copy the variable list from psparse
	country, lang, argCommand, subCommand, addTitle, \
		argQuery, argSortingList, argContentTypes, minprice, maxprice, \
		printTableResults, dontPrintResults, ignorePreviousFetch, \
		reverseResults, getAllDeals, \
		writetext, writereddit, writehtml, writexlsx, operation = psparse.getVars()

	# store-independent functions: list stores, print examples, show user-set preferences, flush db
	if argCommand and argCommand != "watchlist":
		funcMap = {
			"list": listStores, "examples": psinfo.printExamples,
			"preferences": psconfig.checkPreferences,
			"flush": pssql.flush, "flushall": pssql.flush
		}
		func = funcMap[argCommand]
		if argCommand == "list":
			func(conf=allstores)
		elif argCommand == "flush":
			func(dbfile=DBFILE)
		elif argCommand == "flushall":
			func(dbfile=DBFILE, everything=True)
		else:
			func()
		sys.exit()

	# sanity check
	exitCode = prelimCheck(
		country=country, lang=lang, minprice=minprice,
		maxprice=maxprice, conf=allstores, sortingList=argSortingList,
		contentTypes=argContentTypes
	)
	del allstores
	if exitCode == 1:
		sys.exit(1)

	locale = "{}-{}".format(lang, country)
	pssql.maketables(dbfile=DBFILE)
	savedMessages = []

	def fullShebang(deal=None, dealID=None, itemcount=0, isQuery=False, isDeal=False, isWatch=False, pages=0):
		itemlist, tlen, plen, filterMessage = pssql.mainselect(
			dbfile=DBFILE, deal=deal, dealID=dealID, locale=locale,
			sortingList=argSortingList, contentTypes=argContentTypes,
			minprice=minprice, maxprice=maxprice, allcontent=allcontent,
			lang=lang, country=country, reverseResults=reverseResults
		)
		if not itemlist:
			return None

		if not dontPrintResults:
			printitems(itemlist, tlen=tlen, plen=plen, table=printTableResults)

		itemWord = "items"
		if itemcount == 1:
			itemWord = "item"
		if itemcount == 0:
			itemcount = len(itemlist)

		if isDeal:
			printMessage = "fetched {}/{} {} from the '{}' deal. pages: {}"
			printMessage = printMessage.format(len(itemlist), itemcount, itemWord, deal, pages)
		elif isQuery:
			printMessage = "found {} {} for '{}' query"
			printMessage = printMessage.format(itemcount, itemWord, deal)
		elif isWatch:
			printMessage = "fetched {} watchlist {}"
			printMessage = printMessage.format(itemcount, itemWord)
		print(printMessage)

		funcs = [func for func in (writereddit, writehtml, writexlsx, writetext) if func]
		exts = {writereddit: "reddit.txt", writehtml: "html", writexlsx: "xlsx", writetext: "txt"}
		for func in funcs:
			filename = deal.replace("- ", "").replace(" ", ".").lower()
			if isQuery:
				filename = "query." + filename
			filename = "{}.{}.{}.{}".format(filename, lang, country, exts[func])
			filename = filename.replace("..", ".").replace("...", ".")
			if func == writetext:
				savedMessage = func(
					itemlist=itemlist, tlen=tlen, plen=plen,
					lang=lang, country=country, table=printTableResults,
					filterMessage=filterMessage, filename=filename
				)
			elif func == writereddit:
				savedMessage = func(
					itemlist=itemlist, lang=lang, country=country,
					filename=filename, filterMessage=filterMessage
				)
			else:
				savedMessage = func(
					itemlist=itemlist, lang=lang, country=country, deal=deal,
					filename=filename, filterMessage=filterMessage
				)
			savedMessages.append(savedMessage)

	def watchdog(dbfile=None, locale=None, command=None, addtitle=None):
		watchlist(dbfile=dbfile, locale=locale, command=command, addtitle=addtitle)
		if command == "check":
			fullShebang(deal="watchlist", dealID="watchlist", isWatch=True)
			pssql.cleanup(dbfile=dbfile, deal="watchlist", dealID="watchlist", locale=locale)

	def fetchitem(dbfile=None, rawQuery=[], lang=None, country=None):
		queries = " ".join(rawQuery).split(",")
		queries = [q.strip() for q in queries if q.strip()]
		for query in queries:
			getitems(query=query, deal=query, lang=lang, country=country, pagenumber=1, dbfile=dbfile)
			fullShebang(deal=query, dealID=query, isQuery=True)
			if len(queries) > 1 and query != queries[-1] and not dontPrintResults:
				print()
			pssql.cleanup(dbfile=dbfile, deal=query, dealID=query, locale=locale)

	def fetchdeal(dbfile=None, lang=None, country=None, fetchall=None):
		deals = getdeals(lang, country, fetchall=fetchall)
		if not deals:
			return None

		p = multiprocessing.Pool(processes=multiprocessing.cpu_count())
		for deal, dealurl in deals:
			dealID = dealurl.split("/")[-2]
			if ignorePreviousFetch:
				pssql.cleanup(dbfile=dbfile, deal=deal, dealID=dealID, locale=locale)
			# if old results are ignored, fall back to default values 0, 0
			itemcount, pages = pssql.oldcount(dbfile=dbfile, deal=deal, dealID=dealID, locale=locale)
			if itemcount == 0:
				itemcount, pages, pageSize = itercount(dealurl)
				try:
					p.starmap(getitems, zip(
						repeat(dealurl), repeat(deal), range(1, pages + 1),
						repeat(pageSize), repeat(None),
						repeat(lang), repeat(country), repeat(dbfile)
						)
					)
				except TypeError:
					continue
			fullShebang(deal=deal, dealID=dealID, isDeal=True, itemcount=itemcount, pages=pages)
			if len(deals) > 1 and deal != deals[-1][0] and not dontPrintResults:
				print()
		p.close()
		p.join()
	try:
		if operation == "FETCHDEAL":
			fetchdeal(dbfile=DBFILE, lang=lang, country=country, fetchall=getAllDeals)
		elif operation == "FETCHITEM":
			fetchitem(dbfile=DBFILE, lang=lang, country=country, rawQuery=argQuery)
		elif operation == "WATCHDOG":
			watchdog(dbfile=DBFILE, locale=locale, command=subCommand, addtitle=addTitle)

		if savedMessages:
			print("saved output:")
			for message in savedMessages:
				print(" *", message)

	except KeyboardInterrupt:
		print()
		sys.exit()
	except EOFError as err:
		print("\nerror:", err)
		print("likely a broken pipe")
		sys.exit()
	except IndexError:
		print("can't fetch anything. likely there are some site code changes.")
		sys.exit()


if __name__ == "__main__":
	main()
