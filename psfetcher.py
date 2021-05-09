from itertools import repeat
import os
import sys
import sqlite3
import argparse
import json
import multiprocessing
import re
import time
import bs4
import requests
from more_itertools import unique_everseen
import openpyxl


PSFETCHER = os.path.dirname(os.path.realpath(__file__))
DBFILE = os.path.join(PSFETCHER, "psfetcher.db")
CONFIG = os.path.join(PSFETCHER, "lang.json")
PREFERENCES_CONFIG = os.path.join(PSFETCHER, "preferences.json")


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

	Each integer is less than or equals maxval.
	Exit after 3 failed attempts.

	Parameters:
	maxval (int): maximum integer value
	attempt (int): attempt number
	inputMessage (str): input message
	"""
	try:
		messagePool = ["wait, that's illegal!", "believe in yourself", "heh, okay."]
		choices = list(set(input(inputMessage).split()))
		choices = [int(c) for c in choices if c.isdigit() and 0 < int(c) <= maxval]
		if choices == []:
			if attempt >= 3:
				print(messagePool[-1])
				sys.exit()
			print(messagePool[attempt-1])
			choices = choiceCheck(maxval, attempt=attempt+1)
		return choices
	except EOFError as err:
		print("\nwhat in the world! error:", err)
		print("likely a broken pipe")
		sys.exit()


def getdeals(lang, country, fetchall=False):
	"""Return a list of tuples. Each tuple consits of a deal name and its local URL.

	Parameters:
	lang (str): 2-letter language code
	country (str): 2-letter country code
	fetchall (bool): if True, will get all current deals instead of chosen ones
	"""

	def footerDeals(dealname, soup):
		footerDeal = soup.select(".ems-sdk-strand__header")[0]
		if dealname:
			name = dealname
		else:
			name = footerDeal.text.lower()
		url = footerDeal.a.get("href").strip("1")
		deals.extend([(name, url)])
	deals = []
	mainpage = "https://store.playstation.com/{}-{}/deals".format(lang, country)
	soup = webparser(mainpage)
	topDeals = soup.select("div .ems-sdk-collection")[0]
	if topDeals != []:
		for deal in topDeals.find_all("li"):
			name = deal.img.get("alt").replace("[PROMO] ", "").lower()
			url = deal.a.get("href").strip("1")
			if "product" in url:
				print("skipping a single item deal '{}'".format(name))
				continue
			# a deal url within a deal url
			if "- web" in name:
				name = name.replace("- web", "").strip()
				footerDeals(name, webparser(url))
			else:
				deals.extend([(name, url)])
	# "all deals" deal
	footerDeals(None, soup)
	if deals != []:
		if not fetchall:
			[print(ind + 1, deal[0]) for ind, deal in enumerate(deals)]
			choices = choiceCheck(maxval=len(deals))
			deals = [deals[i-1] for i in choices]
		else:
			print("fetching all deals:")
			[print(" *", i[0]) for i in deals]
		return deals


def itercount(dealurl):
	"""Return deal's total number of pages, items, and number of items per page.

	Parameters:
	dealurl (str): deal's local url
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


def getitems(
	dealurl=None, deal=None, pagenumber=None,
	pagesize=0, query=None, lang=None, country=None
):
	"""Return None. Write all results to the SQL database.

	Parameters:
	dealurl (str): deal's local url
	deal (str): deal's name
	pagenumber (int): deal's page number
	pagesize (int): number of items per page
	query (str): a search phrase
	lang (str): 2-letter language code
	country (str): 2-letter country code
	"""
	global DBFILE

	sys.stderr.write("\033[K" + "fetching page {}".format(pagenumber) + "\r")
	sys.stderr.flush()

	if dealurl:
		soup = webparser(dealurl + str(pagenumber))
	elif query:
		url = "https://store.playstation.com/{}-{}/search/{}"
		url = url.format(lang, country, query.replace(" ", "%20"))
		soup = webparser(url)

	dataDump = json.loads(soup.find("script", id="__NEXT_DATA__").string)
	productIdTree = dataDump["props"]["apolloState"]

	productIds = []
	if dealurl:
		# unique child 'CategoryGrid' for json tree:
		# a deal id + lang + country + total number of items already shown
		dealId = dealurl.split("/")[-2]
		continueFrom = 0
		if pagenumber > 1:
			continueFrom = pagenumber * pagesize - pagesize
		categoryJs = "CategoryGrid:{}:{}-{}:{}:{}".format(dealId, lang, country, continueFrom, pagesize)
		for i in productIdTree[categoryJs]["products"]:
			productIds.append(i["id"])
	elif query:
		dealId = query
		for productId in productIdTree:
			locale = ":{}-{}".format(lang, country)
			if productId.startswith("Product") and \
				(productId.endswith(locale) or productId.endswith(":en-us")):
				productIds.append(productId)

	locale = lang + country
	noCurrencyReg = re.compile(r"[0-9,.\s]+")
	connection = sqlite3.connect(DBFILE)
	c = connection.cursor()
	c.execute(
		"create table if not exists psfetcher \
		(id integer primary key autoincrement, titleid blob, title blob, price blob, \
		discount blob, roundprice real, type blob, deal blob, pagenumber integer, dealid blob, locale text)"
	)

	for productId in productIds:
		itemInfo = dataDump["props"]["apolloState"][productId]
		if query:
			if not query.lower() in itemInfo["name"].lower():
				continue
		priceId = itemInfo["price"]["id"]
		priceJs = dataDump["props"]["apolloState"][priceId]
		try:
			price = noCurrencyReg.search(priceJs["discountedPrice"]).group()
			price = price.translate(str.maketrans({" ": None, ",": "."}))
			# fix decimal separator rounding issue: if len after dec. sep. position is >= 3
			decSepPosition = price.find(".") + 1
			if len(price[decSepPosition:]) >= 3:
				price = price.replace(".", "")
			roundPrice = round(float(price), 2)
		except (KeyError, AttributeError, ValueError):
			roundPrice = 0.1
		c.execute(
			"insert into psfetcher (titleid, title, price, roundprice, discount, type, deal, pagenumber, dealid, locale) \
			values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
				itemInfo["id"], itemInfo["name"].strip(),
				priceJs["discountedPrice"], roundPrice,
				str(priceJs["discountText"]),
				itemInfo["localizedStoreDisplayClassification"], deal, pagenumber, dealId, locale
			)
		)
	connection.commit()


def printitems(itemlist, tlen=0, plen=0, table=False):
	"""Return None. Print formatted results from itemlist.

	Parameters:
	itemlist (list): data list of items (dicts)
	tlen (int): title length value used for justification
	plen (int): price length value used for justification
	table (bool): if True, will print table-like results
	"""
	header = "{} | {} | Discount".format("Title".ljust(tlen), "Price".ljust(plen))
	print(header)
	for item in itemlist:
		if table:
			print("-" * round(len(header)))
		itemline = "{} | {} | {}".format(
			item["title"].ljust(tlen),
			item["price"].ljust(plen),
			item["discount"])
		print(itemline)


def writetext(
	itemlist=None, lang=None, country=None, tlen=0, plen=0,
	table=False, filename=None, filterMessage=None
):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts)
	lang (str): 2-letter language code
	country (str): 2-letter country code
	tlen (int): title length value used for justification
	plen (int): price length value used for justification
	table (bool): if True, will print table-like results
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	"""
	header = "{} | {} | Discount\n".format("Title".ljust(tlen), "Price".ljust(plen))
	with open(filename, "w") as output:
		output.write("{}\n".format(filterMessage))
		output.write(header)
		for item in itemlist:
			if table:
				output.write("-" * round(len(header)) + "\n")
			itemline = "{} | {} | {}\n".format(
				item["title"].ljust(tlen),
				item["price"].ljust(plen),
				item["discount"])
			output.write(itemline)
	return filename


def writereddit(
	itemlist=None, lang=None, country=None,
	filename=None, filterMessage=None, name=None
):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts)
	lang (str): 2-letter language code
	country (str): 2-letter country code
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	name (str): deal's name
	"""
	header = "Title | Price | Discount\n---|---|----"
	filterMessage = filterMessage + "\n"
	commentLen = len(header + filterMessage)
	with open(filename, "w") as output:
		output.write("{}\n".format(filterMessage))
		output.write(header)
		for item in itemlist:
			itemline = "\n[{}]({}) | {} | {}".format(
				item["title"],
				"https://store.playstation.com/{}-{}/product/".format(lang, country) + item["id"],
				item["price"],
				item["discount"])
			output.write(itemline)
			commentLen += len(itemline)
			if commentLen > 9800:
				commentLen = len(header)
				output.write("\n\n{}".format(header))
	return filename


def writehtml(
	itemlist=None, lang=None, country=None,
	filename=None, filterMessage=None, name=None
):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts)
	lang (str): 2-letter language code
	country (str): 2-letter country code
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	name (str): deal's name
	"""
	header = (
		"<!DOCTYPE html>"
		"\n<html>"
		"\n<body>"
		"\n<head>"
		"\n\t<meta charset=\"utf-8\">"
		"\n\t<title>%s</title>"
		"\n</head>"
		"\n<style>"
		"\nbody {background-color: #131516;}"
		"\na {text-decoration: none; color: #21618c;}"
		"\nh2, h3, h4 {"
		"\n\tfont-family: courier new;"
		"\n\tcolor: #99a3a4;"
		"\n\ttext-align: center;"
		"\n}"
		"\ntable {"
		"\n\tfont-family: courier new;"
		"\n\tborder-collapse: collapse;"
		"\n\tcolor: #99a3a4;"
		"\n\tmargin-left: auto;"
		"\n\tmargin-right: auto;"
		"\n}"
		"\ntd, th {"
		"\n\ttext-align: left;"
		"\n\tpadding: 5px;"
		"\n}"
		"\ntr:nth-child(even) {"
		"\n\tbackground-color: #202020;"
		"\n}"
		"\n</style>" % name.upper()
	)
	heading = "\n<h2>{} ({}-{} STORE)</h2>".format(name.upper(), lang.upper(), country.upper())
	lowerHeading = "\n<h3>{}</h3>".format(filterMessage)
	tableHeader = (
		"\n<table>"
		"\n\t<tr>\n\t\t<th>Title</th>"
		"\n\t\t<th>Price</th>"
		"\n\t\t<th>Discount</th>"
		"\n\t</tr>"
	)
	productUrl = "https://store.playstation.com/{}-{}/product/".format(lang, country)
	tRow = (
		"\n\t<tr>\n\t\t<th>"
		"<a href=\"{}{}\">{}</a></th>"
		"\n\t\t<th>{}</th>\n\t\t<th>{}</th>\n\t</tr>"
	)
	footer = "\n</table>\n</body>\n</html>:"
	with open(filename, "w") as output:
		[output.write(i) for i in (header, heading, lowerHeading, tableHeader)]
		for item in itemlist:
			output.write(tRow.format(
				productUrl, item["id"],
				item["title"], item["price"], item["discount"]
				)
			)
		output.write(footer)
	return filename


def writexlsx(
	itemlist=None, lang=None, country=None,
	filename=None, filterMessage=None, name=None
):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems()
	deal (str): deal's name
	lang (str): 2-letter language code
	country (str): 2-letter country code
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	name (str): deal's name
	"""
	wb = openpyxl.Workbook()
	sheet = wb.active
	sheet.title = name
	sheet["A1"] = filterMessage
	sheet["A2"] = "Title"
	sheet["B2"] = "Price"
	sheet["C2"] = "Discount"
	sheet["D2"] = "Link"
	productUrl = "https://store.playstation.com/{}-{}/product/".format(lang, country)
	for ind, item in enumerate(itemlist):
		ind += 3
		url = productUrl + item["id"]
		cells = {"A": item["title"], "B": item["price"], "C": item["discount"], "D": url}
		for cell, data in cells.items():
			sheet[cell + str(ind)] = data
	wb.save(filename)
	return filename


if __name__ == "__main__":
	if not os.path.isfile(CONFIG) or not os.access(CONFIG, os.R_OK):
		print("ensure you have '{}' with at least read access".format(CONFIG))
		sys.exit()

	with open(CONFIG, "r") as config:
		allconf = json.loads(config.read())
	allstores = {}
	allcontent = {}
	for lang in allconf.keys():
		allstores[lang] = allconf[lang]["country"]
		allcontent[lang] = allconf[lang]["content"]
	del allconf
	countries = [country for sList in allstores.values() for country in sList]

	parser = argparse.ArgumentParser(
			prog="psfetcher",
			description="Fetch deals or search for game titles in PS Store",
			usage="%(prog)s -s xx [option]", add_help=False,
			formatter_class=argparse.RawTextHelpFormatter)
	requiredArg = parser.add_argument_group("required argument")
	optionalArg = parser.add_argument_group("optional arguments")
	requiredArg.add_argument(
		"-s", "--store", metavar="xx",
		type=str, choices=countries,
		help="2-letter country code"
	)
	requiredArg.add_argument(
		"-l", "--lang", metavar="xx",
		type=str, choices=list(allstores.keys()),
		help="2-letter language code"
	)
	optionalArg.add_argument(
		"-a", "--alldeals", action="store_true",
		help="select all available deals"
	)
	optionalArg.add_argument(
		"-q", "--query", metavar="title", type=str, nargs="+",
		help="search for a title (page 1 results only)")
	optionalArg.add_argument(
		"-f", "--from", dest="min", metavar="N",
		type=int, default=0,
		help="title's minimum price"
	)
	optionalArg.add_argument(
		"-u", "--under", dest="max", metavar="N",
		type=int, default=100000,
		help="title's maximum price"
	)
	optionalArg.add_argument(
		"--type", nargs='+',
		choices=["game", "addon", "currency"],
		help="show only specific content type(s)"
	)
	optionalArg.add_argument(
		"--sort", nargs='+',
		choices=["price", "title", "discount"],
		metavar="{price, title, discount}",
		help="sort results by price, title, or discount"
	)
	optionalArg.add_argument(
		"--reverse", action="store_true",
		help="reversed --sort results"
	)
	optionalArg.add_argument(
		"-t", "--txt", action="store_const",
		const=writetext, dest="writetext",
		help="save results as a text file"
	)
	optionalArg.add_argument(
		"-r", "--reddit", action="store_const",
		const=writereddit, dest="writereddit",
		help="save results as a reddit-friendly comment"
	)
	optionalArg.add_argument(
		"-w", "--web", action="store_const",
		const=writehtml, dest="writehtml",
		help="save results as an HTML document"
	)
	optionalArg.add_argument(
		"-x", "--xlsx", action="store_const",
		const=writexlsx, dest="writexlsx",
		help="save results as an XLSX spreadsheet"
	)
	optionalArg.add_argument(
		"-n", "--noprint", action="store_true",
		help="don't print the results"
	)
	optionalArg.add_argument(
		"--table", action="store_true",
		help="table-like printed/saved results"
	)
	optionalArg.add_argument(
		"-i", "--ignore", action="store_true",
		help="ignore old results"
	)
	optionalArg.add_argument(
		"--list", action="store_true",
		dest="storeslist",
		help="list all language and country codes")
	optionalArg.add_argument(
		"-v", "--version", action="version",
		version="%(prog)s 1.0.4",
		help="show script's version and exit"
	)
	optionalArg.add_argument(
		'-h', '--help', action='help',
		default=argparse.SUPPRESS,
		help="show this help message and exit"
	)

	args = parser.parse_args()
	country = args.store
	lang = args.lang
	argQuery = args.query
	argSortingList = args.sort
	argContentTypes = args.type
	minprice = args.min
	maxprice = args.max
	tablePrintSwitch = args.table
	noPrintSwitch = args.noprint
	ignoreSwitch = args.ignore
	reverseSwitch = args.reverse
	getAllSwitch = args.alldeals
	writetext = args.writetext
	writereddit = args.writereddit
	writehtml = args.writehtml
	writexlsx = args.writexlsx

	if args.storeslist:
		print("language", "|", "country")
		for lang, country in allstores.items():
			print(lang.ljust(len("language")), "|", " ".join(country))
		sys.exit()

	if os.path.isfile(PREFERENCES_CONFIG) and os.access(PREFERENCES_CONFIG, os.R_OK):
		with open(PREFERENCES_CONFIG, "r") as config:
			try:
				prefconf = json.loads(config.read())
			except json.decoder.JSONDecodeError:
				print("{} doesn't follow JSON syntax".format(PREFERENCES_CONFIG))
				sys.exit()

			if not lang and prefconf["language"] is not None:
				lang = prefconf["language"]
				if lang not in allstores.keys():
					print("wrong language set in preferences")
					sys.exit()
			if not country and prefconf["country"] is not None:
				country = prefconf["country"]
				if country not in countries:
					print("wrong country set in preferences")
					sys.exit()

	if not country:
		print("specify the country code")
		sys.exit()
	if not lang:
		print("specify the language code")
		sys.exit()
	if country not in allstores[lang]:
		print("can't combine language code '{}' with country code '{}'".format(lang, country))
		sys.exit()
	if 0 > minprice or minprice > maxprice or \
		(minprice > maxprice and maxprice != parser.get_default('max')):
		print("there there now, be a dear and fix those prices")
		sys.exit()

	def filenameMaker(name, lang, country, ext=None, query=False):
		exts = {writereddit: "reddit.txt", writehtml: "html", writexlsx: "xlsx", writetext: "txt"}
		name = name.replace("- ", "").replace(" ", ".")
		filename = "{}.{}.{}.{}".format(name, lang, country, exts[ext])
		if query:
			filename = "query." + filename
		return filename.lower()

	def getSQL(cursor=True):
		global DBFILE
		if cursor:
			return sqlite3.connect(DBFILE).cursor()
		return sqlite3.connect(DBFILE)

	def cleanupOldFetch(dealId, locale):
		c = getSQL(cursor=False)
		c.cursor().execute("delete from psfetcher where dealid = ? and locale = ?", (dealId, locale))
		c.commit()

	def selectData(dealId, locale):
		global argSortingList, argContentTypes, allcontent, minprice, maxprice
		contentMes = None
		sortMes = None

		priceRangeMes = "price range: "
		if minprice != parser.get_default('min'):
			priceRangeMes += "from {} ".format(minprice)
		if maxprice != parser.get_default('max'):
			priceRangeMes += "under {}".format(maxprice)
		if len(priceRangeMes) == 13:
			priceRangeMes = None

		select = "select title, price, discount, titleid from psfetcher"
		select += " where roundprice between {} and {} and dealid = '{}' and locale = '{}'".format(minprice, maxprice, dealId, locale)

		if argContentTypes:
			ctypes = []
			for ctype in argContentTypes:
				ctypes += allcontent[lang][ctype]
			placeholders = "?" * len(ctypes)
			placeholders = ",".join(placeholders)
			select += " and psfetcher.type in ({})".format(placeholders)
			contentMes = "content: {}".format(", ".join(argContentTypes))
		if argSortingList:
			argSortingList = list(unique_everseen(argSortingList))
			sortingList = ["roundprice" if i == "price" else i for i in argSortingList]
			order = {False: " asc", True: " desc"}
			order = order[reverseSwitch]
			select += " order by " + "{}, ".format(order).join(sortingList) + order
			sortMes = "sorted by {}".format(" then by ".join(argSortingList))
			if reverseSwitch:
				sortMes += " in reverse"

		try:
			c = getSQL()
			titleSelect = "select length(title) from psfetcher where dealid = ? and locale = ? order by length(title) desc limit 1"
			maxTitleLen, = c.execute(titleSelect, (dealId, locale)).fetchone()
			priceSelect = "select length(price) from psfetcher where dealid = ? and locale = ? order by length(price) desc limit 1"
			maxPriceLen, = c.execute(priceSelect, (dealId, locale)).fetchone()

			itemlist = []
			if argContentTypes:
				select = c.execute(select, ctypes)
			else:
				select = c.execute(select)
			for title, price, discount, titleid in select.fetchall():
				rawdata = {}
				rawdata["title"] = title
				rawdata["price"] = price
				rawdata["discount"] = discount
				rawdata["id"] = titleid
				itemlist.append(rawdata)

			today = time.strftime("%Y %b %d")
			filterMessage = "{} titles | generated at {}".format(len(itemlist), today)
			messages = [m for m in (sortMes, priceRangeMes, contentMes) if m]
			for message in messages:
				filterMessage += " | {}".format(message)
			return itemlist, maxTitleLen, maxPriceLen, filterMessage

		except TypeError:
			return None, 0, 0, None

	def checkOldData(dealId, locale):
		try:
			c = getSQL()
			oldcount, = c.execute("select count(title) from psfetcher where dealid = ? and locale = ?", (dealId, locale)).fetchone()
			if oldcount > 0:
				totalpages, = c.execute("select max(pagenumber) from psfetcher where dealid = ? and locale = ?", (deal, locale)).fetchone()
				return oldcount, totalpages
			return 0, 0
		except sqlite3.OperationalError:
			return 0, 0

	# outside due to mp
	savedMessages = []

	def fullShebang(printQuery=False, printDeal=False):
		global maxPriceLen, maxTitleLen, data
		funcs = [func for func in (writereddit, writehtml, writexlsx, writetext) if func]
		for func in funcs:
			filename = filenameMaker(deal, lang, country, ext=func, query=querySwitch)
			if func != writetext:
				savedMessage = func(
					itemlist=data, lang=lang, country=country, name=deal,
					filename=filename, filterMessage=filterMessage
				)
			elif func == writetext:
				savedMessage = func(
					itemlist=data, tlen=maxTitleLen, plen=maxPriceLen,
					lang=lang, country=country, table=tablePrintSwitch,
					filterMessage=filterMessage, filename=filename
				)
			savedMessages.append(savedMessage)

		if not noPrintSwitch:
			printitems(data, tlen=maxTitleLen, plen=maxPriceLen, table=tablePrintSwitch)
		if printDeal:
			printMessage = "fetched {}/{} items from the '{}' deal. pages: {}"
			printMessage = printMessage.format(len(data), itemcount, deal, pages)
		elif printQuery:
			printMessage = "found {} items for '{}' query"
			printMessage = printMessage.format(len(data), deal)
		print(printMessage)

	try:
		locale = lang + country
		if argQuery:
			query = " ".join(argQuery).split(",")
			query = [q for q in query if q.strip()]
			for q in query:
				deal = dealId = q.strip()
				querySwitch = True
				getitems(query=deal, deal=deal, lang=lang, country=country, pagenumber=1)
				data, maxTitleLen, maxPriceLen, filterMessage = selectData(dealId, locale)
				if data:
					fullShebang(printQuery=True)
					if len(query) > 1 and q != query[-1] and not noPrintSwitch:
						print()
				cleanupOldFetch(dealId, locale)
		else:
			try:
				deals = getdeals(lang, country, fetchall=getAllSwitch)
			except IndexError:
				print("can't fetch anything. likely there are some site code changes.")
				sys.exit()

			querySwitch = False
			p = multiprocessing.Pool(processes=multiprocessing.cpu_count())
			for deal, dealurl in deals:
				dealId = dealurl.split("/")[-2]
				if ignoreSwitch:
					cleanupOldFetch(dealId, locale)
					oldcount = 0
				else:
					oldcount, totalpages = checkOldData(dealId, locale)
				if oldcount == 0:
					itemcount, pages, pageSize = itercount(dealurl)
					try:
						p.starmap(getitems, zip(
							repeat(dealurl), repeat(deal), range(1, pages + 1),
							repeat(pageSize), repeat(None),
							repeat(lang), repeat(country),
							)
						)
					except TypeError:
						continue
				else:
					itemcount = oldcount
					pages = totalpages
				data, maxTitleLen, maxPriceLen, filterMessage = selectData(dealId, locale)
				if data:
					fullShebang(printDeal=True)
					if len(deals) > 1 and deal != deals[-1][0] and not noPrintSwitch:
						print()
			p.close()
			p.join()
		if savedMessages:
			print("saved output:")
			[print(" *", m) for m in savedMessages]
	except KeyboardInterrupt:
		print()
		sys.exit()
