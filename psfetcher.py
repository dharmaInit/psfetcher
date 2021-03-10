from itertools import repeat
from operator import itemgetter
import os
import sys
import argparse
import json
import multiprocessing
import re
import time
import yaml
import bs4
import requests
from more_itertools import unique_everseen
import openpyxl


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
	try:
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
	except IndexError as err:
		if deals == []:
			errorMessage = "can't fetch anything at the moment, sorry.\nerror: "
			errorMessage += str(err)
			errorMessage += "\nlikely there are some site code changes"
			print(errorMessage)
			sys.exit()


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
	dealurl=None, pagenumber=None, pagesize=0, query=None, lang=None,
	country=None, ctype=None, minprice=0, maxprice=10000
):
	"""Return two lists: a list of dictionaries, and a list of tuples.

	Each dict in the first list contains information about a specific item.
	The second list is a tuple of maximum length values (title, price) from the whole page.
	If it's a query, results are only from page 1.

	Parameters:
	dealurl (str): deal's local url
	pagenumber (int): deal's page number
	pagenumber (int): number of item per page
	query (str): a search phrase
	lang (str): 2-letter language code
	country (str): 2-letter country code
	ctype (list): a list of all selected content types
	minprice (int): minimum price of a title
	maxprice (int): maximum price of a title
	"""
	results = []
	lenPair = []
	productIds = []
	noCurrencyReg = re.compile(r"[0-9,.\s]+")

	if dealurl:
		soup = webparser(dealurl + str(pagenumber))
	elif query:
		url = "https://store.playstation.com/{}-{}/search/{}"
		url = url.format(lang, country, query.replace(" ", "%20"))
		soup = webparser(url)

	dataDump = json.loads(soup.find("script", id="__NEXT_DATA__").string)
	productIdTree = dataDump["props"]["apolloState"]

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
		for productId in productIdTree:
			locale = ":{}-{}".format(lang, country)
			if productId.startswith("Product") and \
				(productId.endswith(locale) or productId.endswith(":en-us")):
				productIds.append(productId)

	for productId in productIds:
		itemInfo = dataDump["props"]["apolloState"][productId]
		if query:
			if not query.lower() in itemInfo["name"].lower():
				continue
		rawdata = {}
		rawdata["type"] = itemInfo["localizedStoreDisplayClassification"]
		if ctype:
			if rawdata["type"] not in ctype:
				continue
		rawdata["id"] = itemInfo["id"]
		rawdata["name"] = itemInfo["name"]
		priceId = itemInfo["price"]["id"]
		priceJs = dataDump["props"]["apolloState"][priceId]
		rawdata["price"] = priceJs["discountedPrice"]
		rawdata["discount"] = str(priceJs["discountText"])
		try:
			price = noCurrencyReg.search(rawdata["price"]).group()
			price = price.translate(str.maketrans({" ": None, ",": "."}))
			# fix decimal separator rounding issue: if len after dec. sep. position is >= 3
			decSepPos = price.find(".") + 1
			if len(price[decSepPos:]) >= 3:
				price = price.replace(".", "")
			roundPrice = round(float(price), 2)
		except (KeyError, AttributeError, ValueError):
			roundPrice = 0.1

		if minprice < roundPrice < maxprice:
			rawdata["name"] = rawdata["name"].strip()
			lenTitlePrice = (len(rawdata["name"]), len(rawdata["price"]))
			lenPair.append(lenTitlePrice)
			rawdata.update({"roundprice": roundPrice})
			results.append(rawdata)
	lenPair = [max(i) for i in zip(*lenPair)]
	return results, lenPair


def printitems(itemlist, tlen=0, plen=0, table=False):
	"""Return None. Print formatted results from itemlist.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems()
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
			item["name"].ljust(tlen),
			item["price"].ljust(plen),
			item["discount"])
		print(itemline)


def writetext(
	itemlist=None, lang=None, country=None, tlen=0, plen=0,
	table=False, filename=None, filterMessage=None
):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems()
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
				item["name"].ljust(tlen),
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
	itemlist (list): data list of items (dicts) returned from getitems()
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
				item["name"],
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
	itemlist (list): data list of items (dicts) returned from getitems()
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
				item["name"], item["price"], item["discount"]
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
		cells = {"A": item["name"], "B": item["price"], "C": item["discount"], "D": url}
		for cell, data in cells.items():
			sheet[cell + str(ind)] = data
	wb.save(filename)
	return filename


if __name__ == "__main__":
	PSFETCHER = os.path.dirname(os.path.realpath(__file__))
	CONFIG = "lang.yaml"
	CONFIG = os.path.join(PSFETCHER, CONFIG)
	if not os.path.isfile(CONFIG) or not os.access(CONFIG, os.R_OK):
		print("ensure you have '{}' with at least read access".format(CONFIG))
		sys.exit()
	with open(CONFIG) as config:
		allconf = yaml.load(config, Loader=yaml.FullLoader)
	allstores = {}
	allcontent = {}
	for lang in allconf.keys():
		allstores[lang] = allconf[lang]["country"]
		allcontent[lang] = allconf[lang]["content"]
	countries = [country for sList in allstores.values() for country in sList]

	helpMessagePool = {
		"country": "2-letter country code",
		"language": "2-letter language code (default is en)",
		"alldeals": "choose all available deals without entering the interactive mode",
		"query": "search for a title in a store (page 1 results only)",
		"minprice": "title's minimum price",
		"maxprice": "title's maximum price",
		"sort": "sort results by price, title, or discount",
		"reverse": "reversed --sort results",
		"type": "show only specific content type(s)",
		"writetext": "save results as a text file",
		"writereddit": "save results as a reddit-friendly comment",
		"writehtml": "save results as an HTML document",
		"writexlsx": "save results as an XLSX spreadsheet",
		"noPrintSwitch": "don't print the results",
		"tablePrintSwitch": "table-like printed/saved results",
		"list": "list all language and country codes",
		"version": "show script's version and exit",
		"help": "show this help message and exit"
	}

	parser = argparse.ArgumentParser(
			prog="psfetcher",
			description="Fetch deals or search for game titles in a PS Store",
			usage="%(prog)s -s xx [option]", add_help=False,
			formatter_class=argparse.RawTextHelpFormatter)
	requiredArg = parser.add_argument_group("required argument")
	optionalArg = parser.add_argument_group("optional arguments")
	requiredArg.add_argument("-s", "--store", metavar="xx",
				type=str, choices=countries,
				help=helpMessagePool["country"])
	optionalArg.add_argument("-l", "--lang", metavar="xx",
				type=str, choices=list(allstores.keys()), default="en",
				help=helpMessagePool["language"])
	optionalArg.add_argument("-a", "--alldeals", action="store_true",
				help=helpMessagePool["alldeals"])
	optionalArg.add_argument("-q", "--query", metavar="title",
				type=str, nargs="+",
				help=helpMessagePool["query"])
	optionalArg.add_argument("-f", "--from", dest="min", metavar="N",
				type=int, default=0,
				help=helpMessagePool["minprice"])
	optionalArg.add_argument("-u", "--under", dest="max", metavar="N",
				type=int, default=100000,
				help=helpMessagePool["maxprice"])
	optionalArg.add_argument("--type", nargs='+',
				choices=["game", "addon", "currency"],
				help=helpMessagePool["type"]),
	optionalArg.add_argument("--sort", nargs='+',
				choices=["price", "title", "discount"],
				metavar="{price, title, discount}",
				help=helpMessagePool["sort"])
	optionalArg.add_argument("--reverse", action="store_true",
				help=helpMessagePool["reverse"])
	optionalArg.add_argument("-t", "--txt", action="store_const",
				const=writetext, dest="writetext",
				help=helpMessagePool["writetext"])
	optionalArg.add_argument("-r", "--reddit", action="store_const",
				const=writereddit, dest="writereddit",
				help=helpMessagePool["writereddit"])
	optionalArg.add_argument("-w", "--web", action="store_const",
				const=writehtml, dest="writehtml",
				help=helpMessagePool["writehtml"])
	optionalArg.add_argument("-x", "--xlsx", action="store_const",
				const=writexlsx, dest="writexlsx",
				help=helpMessagePool["writexlsx"])
	optionalArg.add_argument("-n", "--noprint", action="store_true",
				help=helpMessagePool["noPrintSwitch"])
	optionalArg.add_argument("--table", action="store_true",
				help=helpMessagePool["tablePrintSwitch"])
	optionalArg.add_argument("--list", action="store_true",
				dest="storeslist",
				help=helpMessagePool["list"])
	optionalArg.add_argument("-v", "--version", action="version",
				version="%(prog)s 1.0.3",
				help=helpMessagePool["version"])
	optionalArg.add_argument('-h', '--help', action='help',
				default=argparse.SUPPRESS,
				help=helpMessagePool["help"])

	args = parser.parse_args()
	country = args.store
	lang = args.lang
	getAll = args.alldeals
	argQuery = args.query
	argSortingList = args.sort
	argReverse = args.reverse
	argContentTypes = args.type
	minprice = args.min
	maxprice = args.max
	tablePrintSwitch = args.table
	noPrintSwitch = args.noprint
	writetext = args.writetext
	writereddit = args.writereddit
	writehtml = args.writehtml
	writexlsx = args.writexlsx

	# list all and exit
	if args.storeslist:
		print("language", "|", "country")
		for lang, country in allstores.items():
			print(lang.ljust(len("language")), "|", " ".join(country))
		sys.exit()

	# country and lang sanity check
	if not country:
		print("specify the country code")
		sys.exit()
	if country not in allstores[lang]:
		print("can't combine language code '{}' with country code '{}'".format(lang, country))
		sys.exit()

	# price sanity check
	if 0 > minprice or minprice > maxprice or \
		(minprice > maxprice and maxprice != parser.get_default('max')):
		print("there there now, be a dear and fix those prices")
		sys.exit()

	# apply content filter: doesn't go to fillterMessages() because it's pre-processing
	ctypes = []
	contentMes = None
	if argContentTypes:
		for ctype in argContentTypes:
			ctypes += allcontent[lang][ctype]
		contentMes = "content: {}".format(", ".join(argContentTypes))

	def filenameMaker(name, lang, country, ext=None, query=False):
		exts = {writereddit: "reddit.txt", writehtml: "html", writexlsx: "xlsx", writetext: "txt"}
		name = name.replace(" ", ".").replace("-", ".")
		filename = "{}.{}.{}.{}".format(name, lang, country, exts[ext])
		if query:
			filename = "query." + filename
		return filename.lower()

	def filterMessages():
		# price range filter message
		priceRangeMes = "price range: "
		if minprice != parser.get_default('min'):
			priceRangeMes += "from {} ".format(minprice)
		if maxprice != parser.get_default('max'):
			priceRangeMes += "under {}".format(maxprice)
		if len(priceRangeMes) == 13:
			priceRangeMes = None

		# sorting by price, title and discount + message
		sortMes = None
		global argSortingList
		if argSortingList:
			argSortingList = list(unique_everseen(argSortingList))
			sortingHat = {"price": "roundprice", "title": "name", "discount": "discount"}
			sortingUnique = [sortingHat[i] for i in argSortingList]
			data.sort(key=itemgetter(*sortingUnique), reverse=argReverse)
			sortMes = "sorted by {}".format(" then by ".join(argSortingList))
			if argReverse:
				sortMes += " in reverse"

		today = time.strftime("%Y %b %d")
		filterMessage = "{} titles | generated at {}".format(len(data), today)
		for message in (sortMes, priceRangeMes, contentMes):
			if message:
				filterMessage += " | {}".format(message)
		return filterMessage

	# outside due to mp
	savedMessages = []

	def fullShebang(printQuery=False, printDeal=False):
		for func in (writereddit, writehtml, writexlsx, writetext):
			if func:
				filename = filenameMaker(deal, lang, country, ext=func, query=querySwitch)
				if func != writetext:
					savedMessage = func(
						itemlist=data, lang=lang, country=country, name=deal,
						filename=filename, filterMessage=filterMessage
					)
				elif func == writetext:
					savedMessage = func(
						itemlist=data, tlen=lenPair[0], plen=lenPair[1],
						lang=lang, country=country, table=tablePrintSwitch,
						filterMessage=filterMessage, filename=filename
					)
				savedMessages.append(savedMessage)

		if not noPrintSwitch:
			if not printQuery:
				print()
			printitems(data, tlen=lenPair[0], plen=lenPair[1], table=tablePrintSwitch)
		if printDeal:
			printMessage = "fetched {}/{} items from the '{}' deal. pages: {}"
			printMessage = printMessage.format(len(data), itemcount, deal, pages)
		elif printQuery:
			printMessage = "found {} items for '{}' query"
			printMessage = printMessage.format(len(data), deal)
		print(printMessage)

	try:
		if argQuery:
			deal = query = " ".join(argQuery)
			querySwitch = True
			data, lenPair = getitems(
				query=query, lang=lang, ctype=ctypes,
				country=country, minprice=minprice, maxprice=maxprice
			)
			if data:
				filterMessage = filterMessages()
				fullShebang(printQuery=True)
			else:
				print("try another query or retweak the filters")
		else:
			deals = getdeals(lang, country, fetchall=getAll)
			querySwitch = False
			p = multiprocessing.Pool(processes=multiprocessing.cpu_count())
			for deal, dealurl in deals:
				itemcount, pages, pageSize = itercount(dealurl)
				try:
					datalists = p.starmap_async(getitems, zip(
						repeat(dealurl), range(1, pages + 1),
						repeat(pageSize), repeat(None),
						repeat(lang), repeat(country),
						repeat(ctypes),
						repeat(minprice), repeat(maxprice)
						)
					).get()
				except TypeError:
					print("nothing for '{}'. likely due to a site code change".format(deal))
					continue
				data = []
				lenPairs = []
				for itemlist, lenPair in datalists:
					data.extend(itemlist)
					if lenPair != []:
						lenPairs.extend([lenPair])
				datalists.clear()
				if data:
					data = list(unique_everseen(data))
					filterMessage = filterMessages()
					lenPair = [max(i) for i in zip(*lenPairs)]
					fullShebang(printDeal=True)
				else:
					print("nothing for '{}'".format(deal))
			p.close()
			p.join()
		if savedMessages:
			print("saved output:")
			[print(" *", m) for m in savedMessages]
	except KeyboardInterrupt:
		print()
		sys.exit()
