from itertools import repeat
from operator import itemgetter
from random import randrange
import argparse
import json
import multiprocessing
import re
import sys
import time
import bs4
import requests
from more_itertools import unique_everseen


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


def getdeals(lang, store, fetchall=False):
	"""Return a list of tuples. Each tuple consits of a deal name and its local URL.

	Parameters:
	lang (str): 2-letter language code
	store (str): 2-letter country code
	fetchall (bool): if True, will get all current deals instead of chosen ones
	"""

	def footerDeals(dealname, soup):
		footerDeal = soup.select(".ems-sdk-strand__header")[0]
		if dealname:
			footerDealName = dealname
		else:
			footerDealName = footerDeal.text.lower()
		footerDealLink = footerDeal.a.get("href").strip("1")
		deals.extend([(footerDealName, footerDealLink)])
	try:
		deals = []
		url = "https://store.playstation.com/{}-{}/deals".format(lang, store)
		soup = webparser(url)
		topDeals = soup.select("div .ems-sdk-collection")[0]
		if topDeals != []:
			for deal in topDeals.find_all("li"):
				dealName = deal.img.get("alt").replace("[PROMO] ", "").lower()
				dealLink = deal.a.get("href").strip("1")
				# a deal url within a deal url
				if "- web" in dealName:
					dealName = dealName.replace("- web", "").strip()
					footerDeals(dealName, webparser(dealLink))
				else:
					deals.extend([(dealName, dealLink)])
		# "all sales" deal
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


def itercount(deal, dealurl, unrealpage=100):
	"""Return deal's last page number as an integer.

	Parameters:
	deal (str): deal's name
	dealurl (str): deal's local url
	unrealpage (int): an unlikely page number for a deal
	"""
	try:
		soup = webparser(dealurl + str(unrealpage))
		lastPageClass = ".ems-sdk-grid-paginator__button.ems-sdk-grid-paginator__number-button"
		lastPageClass += ".psw-button.psw-content-button"
		lastPage = int(soup.select("div {}".format(lastPageClass))[-1].text)
		return lastPage
	except IndexError:
		print("deal '{}' has a single item, skipping".format(deal))


def getitems(dealurl, pagenumber, minprice=0, maxprice=10000):
	"""Return two lists: a list of dictionaries, and a list of tuples.

	Each dict in the first list contains information about a specific item.
	The second list is a tuple of maximum length values (title, price) from the whole page.

	Parameters:
	dealurl (str): deal's local url
	pagenumber (int): deal's page number
	minprice (int): minimum price of a title
	maxprice (int): maximum price of a title
	"""
	results = []
	lenPair = []
	noCurrencyReg = re.compile(r"[0-9,.\s]+")
	soup = webparser(dealurl + str(pagenumber))
	links = soup.select("div .ems-sdk-grid")[0]
	for li in links.find_all("li"):
		rawdata = json.loads(li.a.get("data-telemetry-meta"))
		try:
			price = noCurrencyReg.search(rawdata["price"]).group()
			price = price.translate(str.maketrans({" ": None, ",": "."}))
			# fix decimal separator rounding issue: if len after dec. sep. position is >= 3
			decSepPos = price.find(".") + 1
			if len(price[decSepPos:]) >= 3:
				price = price.replace(".", "")
			roundPrice = round(float(price), 2)
		except KeyError:
			rawdata.update({"price": "None"})
			roundPrice = 0.1
		except AttributeError:
			roundPrice = 0.1
		try:
			discount = li.select("div .discount-badge__container.psw-l-anchor")
			rawdata.update({"discount": discount[0].text})
		except (KeyError, IndexError):
			rawdata.update({"discount": "None"})
		if minprice < roundPrice < maxprice:
			rawdata["name"] = rawdata["name"].strip()
			lenTitlePrice = (len(rawdata["name"]), len(rawdata["price"]))
			lenPair.append(lenTitlePrice)
			rawdata.update({"roundprice": roundPrice})
			rawdata.pop("index")
			results.append(rawdata)
	lenPair = [max(i) for i in zip(*lenPair)]
	return results, lenPair


def searchitems(query, lang, store, minprice=0, maxprice=10000):
	"""Return two lists: a list of dictionaries, and a list of tuples.

	Each dict in the first list contains information about a specific item.
	The second list is a tuple of maximum length values (title, price) from the whole page.
	Results are from page 1 only.

	Parameters:
	query (str): a search phrase
	lang (str): 2-letter language code
	store (str): 2-letter country code
	minprice (int): minimum price of a title
	maxprice (int): maximum price of a title
	"""
	results = []
	lenPair = []
	url = "https://store.playstation.com/{}-{}/search/{}"
	url = url.format(lang, store, query.replace(" ", "%20"))
	soup = webparser(url)
	queryJson = list(soup.select("#__NEXT_DATA__")[0])[0]
	parsedJson = json.loads(queryJson)
	parentJson = parsedJson["props"]["apolloState"]
	noCurrencyReg = re.compile(r"[0-9,.\s]+")
	for childJson in parentJson:
		if childJson.startswith("Product") and \
			(childJson.endswith(":{}-{}".format(lang, store)) or childJson.endswith(":en-us")):
			curLevel = parentJson[childJson]
			title = curLevel["name"]
			if query.lower() in title.lower() and curLevel["price"] is not None:
				gid = curLevel["id"]
				priceId = curLevel["price"]["id"]
				priceRaw = parentJson[priceId]
				try:
					price = noCurrencyReg.search(priceRaw["discountedPrice"]).group()
					price = price.translate(str.maketrans({" ": None, ",": "."}))
					# fix decimal separator rounding issue: if len after dec. sep. position is >= 3
					decSepPos = price.find(".") + 1
					if len(price[decSepPos:]) >= 3:
						price = price.replace(".", "")
					roundPrice = round(float(price), 2)
				except AttributeError:
					roundPrice = 0.1
				if minprice < roundPrice < maxprice:
					price = priceRaw["discountedPrice"]
					discount = str(priceRaw["discountText"])
					lenTitlePrice = (len(title), len(price))
					lenPair.append(lenTitlePrice)
					results.append({
						"id": gid, "name": title,
						"price": price, "discount": discount,
						"roundprice": roundPrice
						}
					)
	lenPair = [max(i) for i in zip(*lenPair)]
	return results, lenPair


def printitems(itemlist, tlen=0, plen=0, table=False):
	"""Return None. Print formatted results from itemlist.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems() or searchitems()
	tlen (int): title length value used for justification
	plen (int): price length value used for justification
	table (bool): if True, will print table-like results
	"""
	header = "{} | {} | Discount".format("Title".ljust(tlen), "Price".ljust(plen))
	print(header)
	for item in itemlist:
		if table: print("-" * round(len(header)))
		itemline = "{} | {} | {}".format(
			item["name"].ljust(tlen),
			item["price"].ljust(plen),
			item["discount"])
		print(itemline)


def writetext(itemlist, deal, lang, store, tlen=0, plen=0, genDate=None, table=False, msort=None, prange=None, query=False):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems() or searchitems()
	deal (str): deal's name
	lang (str): store's 2-letter language code
	store (str): store's 2-letter country code
	tlen (int): title length value used for justification
	plen (int): price length value used for justification
	genDate(str): a date used a file's generation date
	table (bool): if True, will print table-like results
	msort (str): a message containing itemlist's sorting order
	prange (str): a message containing user-defined price range
	query (bool): if True, output's filename will start with the word "query"
	"""
	header = "{} | {} | Discount\n".format("Title".ljust(tlen), "Price".ljust(plen))
	filename = "{}.{}.{}.txt".format(deal.replace(" ", "."), lang, store).lower()
	if query: filename = "query." + filename
	filtersMessage = "{} titles | generated at {}".format(len(itemlist), genDate)
	if msort: filtersMessage += " | {}".format(msort)
	if prange: filtersMessage += " | {}".format(prange)
	with open(filename, "w") as output:
		output.write("{}\n".format(filtersMessage))
		output.write(header)
		for item in itemlist:
			if table: output.write("-" * round(len(header)) + "\n")
			itemline = "{} | {} | {}\n".format(
				item["name"].ljust(tlen),
				item["price"].ljust(plen),
				item["discount"])
			output.write(itemline)
	return filename


def writereddit(itemlist, deal, lang, store, genDate=None, msort=None, prange=None, query=False):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems() or searchitems()
	deal (str): deal's name
	lang (str): store's 2-letter language code
	store (str): store's 2-letter country code
	genDate(str): a date used a file's generation date
	msort (str): a message containing itemlist's sorting order
	prange (str): a message containing user-defined price range
	query (bool): if True, output's filename will start with the word "query"
	"""
	header = "Title | Price | Discount\n---|---|----"
	filename = "{}.{}.{}.reddit.txt".format(deal.replace(" ", "."), lang, store).lower()
	if query: filename = "query." + filename
	filtersMessage = "{} titles | generated at {}".format(len(itemlist), genDate)
	if msort: filtersMessage += " | {}".format(msort)
	if prange: filtersMessage += " | {}".format(prange)
	filtersMessage = filtersMessage + "\n"
	commentLen = len(header + filtersMessage)
	with open(filename, "w") as output:
		output.write("{}\n".format(filtersMessage))
		output.write(header)
		for item in itemlist:
			itemline = "\n[{}]({}) | {} | {}".format(
				item["name"],
				"https://store.playstation.com/{}-{}/product/".format(lang, store) + item["id"],
				item["price"],
				item["discount"])
			output.write(itemline)
			commentLen += len(itemline)
			if commentLen > 9800:
				commentLen = len(header)
				output.write("\n\n{}".format(header))
	return filename


def writehtml(itemlist, deal, lang, store, genDate=None, msort=None, prange=None, query=False):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems() or searchitems()
	deal (str): deal's name
	lang (str): store's 2-letter language code
	store (str): store's 2-letter country code
	genDate(str): a date used a file's generation date
	msort (str): a message containing itemlist's sorting order
	prange (str): a message containing user-defined price range
	query (bool): if True, output's filename will start with the word "query"
	"""
	filename = "{}.{}.{}.html".format(deal.replace(" ", "."), lang, store).lower()
	if query: filename = "query." + filename
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
		"\n</style>" % deal.upper()
	)
	heading = "\n<h2>{} ({}-{} STORE)</h2>".format(deal.upper(), lang.upper(), store.upper())
	lowerHeading = "{} titles".format(len(itemlist))
	if msort: lowerHeading += " | {}".format(msort)
	if prange: lowerHeading += " | {}".format(prange)
	lowerHeading = "\n<h3>{}</h3>".format(lowerHeading)
	generation = "\n<h4>generated at {}</h4>".format(genDate)
	tableHeader = (
		"\n<table>"
		"\n\t<tr>\n\t\t<th>Title</th>"
		"\n\t\t<th>Price</th>"
		"\n\t\t<th>Discount</th>"
		"\n\t</tr>"
	)
	productUrl = "https://store.playstation.com/{}-{}/product/".format(lang, store)
	tableRow = (
		"\n\t<tr>\n\t\t<th>"
		"<a href=\"{}{}\">{}</a></th>"
		"\n\t\t<th>{}</th>\n\t\t<th>{}</th>\n\t</tr>"
	)
	footer = "\n</table>\n</body>\n</html>"
	with open(filename, "w") as output:
		[output.write(i) for i in (header, heading, lowerHeading, generation, tableHeader)]
		for item in itemlist:
			output.write(tableRow.format(productUrl, item["id"], item["name"], item["price"], item["discount"]))
		output.write(footer)
	return filename


def randomNothing(mtype=0):
	"""Return a random string message from one of the two message lists.

	Default returned message type is from the first list when nothing is found.
	The second message type is from the second list when user forgot something.

	Parameters:
	mtype(int): an integer to choose a list (can be 0 or 1 only)
	"""
	nothingMuch = [
		"haha nothing.", "nothing. huh.", "ayeeee there's nothing.",
		"dusty nothing.", "wait, nothing?", "are we doing this or what?",
		"nada.", "naught. that ain't right.", "lots of no results.",
		"hmmm. nothing.", "it's your lucky day (not).", "nothing. maybe it's my fault.",
		"well, we used all that RAM for nothing.", "hehe nothing.", "beautiful day, innit?",
		"tomorrow might bring a better luck.", "what are we looking at?",
		"no can do.", "harder better faster wronger.", "sike! that's the wrong numba!"
	]
	tooMuchMemory = [
		"haha wasting RAM is fun", "you've got too much memory on your hands",
		"now why did you do that i wonder", "say, is this what people do?",
		"01101110 01101111 01110100 01101000 01101001 01101110 01100111",
		"randomly accessed memories with nothing to show for it", "was it all worth it?",
		"well that was... uneventful", "do you think people would do that? just go and waste RAM?",
		"accidentally a there", "haha you're funny", "is it possible you've forgotten something?"
	]
	mtypes = [(0, nothingMuch), (1, tooMuchMemory)]
	messagePool = mtypes[mtype][1]
	semiRandom = randrange(len(messagePool))
	return messagePool[semiRandom]


if __name__ == "__main__":
	languages = ["da", "de", "en", "es", "fi", "fr", "it", "nl", "no", "pl", "pt", "sv", "ru"]
	stores = [
		"at", "be", "bg", "ca", "cy", "cz",
		"de", "dk", "es", "fi", "fr", "gb",
		"gr", "hr", "hu", "ie", "in", "is",
		"it", "lu", "mt", "nl", "no", "pl",
		"pt", "ro", "se", "si", "sk", "us", "ru"
	]
	allstores = {
		"de": ["at", "de", "lu"],
		"nl": ["be", "nl"],
		"fr": ["be", "ca", "fr", "lu"],
		"en": [
			"bg", "ca", "hr", "cy", "cz", "dk", "fi", "gr", "hu", "is", "ie",
			"in", "mt", "no", "pl", "ro", "sk", "si", "se", "gb", "us"
		],
		"da": ["dk"], "fi": ["fi"], "it": ["it"], "no": ["no"], "pl": ["pl"],
		"pt": ["pt"], "es": ["es"], "sv": ["se"], "ru": ["ru"]
	}
	helpMessagePool = {
		"store": "store's 2-letter country code",
		"language": "store's 2-letter language code (default is en)",
		"alldeals": "choose all available deals without entering the interactive mode",
		"query": "search for a title in a store (page 1 results only)",
		"minprice": "title's minimum price",
		"maxprice": "title's maximum price",
		"sort": "sort results by price, title, or discount",
		"reverse": "reversed --sort results",
		"writetext": "save results as a text file",
		"writereddit": "save results as a reddit-friendly comment",
		"writehtml": "save results as a simply formatted HTML document",
		"noprint": "don't print the results",
		"tableprint": "table-like printed/saved results",
		"list": "list all language and country codes",
		"version": "show script's version and exit",
		"help": "show this help message and exit"
	}

	def storelist():
		print("language", "|", "country")
		for langcode, ccode in allstores.items():
			print(langcode.ljust(len("language")), "|", " ".join(ccode))

	parser = argparse.ArgumentParser(
			prog="psfetcher",
			description="Fetch deals or search for game titles in a PS Store",
			usage="%(prog)s -s xx [option]", add_help=False,
			formatter_class=argparse.RawTextHelpFormatter)
	requiredArg = parser.add_argument_group("required argument")
	optionalArg = parser.add_argument_group("optional arguments")
	requiredArg.add_argument("-s", "--store", metavar="xx",
				type=str, choices=stores,
				help=helpMessagePool["store"])
	optionalArg.add_argument("-l", "--lang", metavar="xx",
				type=str, choices=languages, default="en",
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
	optionalArg.add_argument("-n", "--noprint", action="store_true",
				help=helpMessagePool["noprint"])
	optionalArg.add_argument("--table", action="store_true",
				help=helpMessagePool["tableprint"])
	optionalArg.add_argument("--list", action="store_const",
				const=storelist, dest="storelist",
				help=helpMessagePool["list"])
	optionalArg.add_argument("-v", "--version", action="version",
				version="%(prog)s 1.0.2",
				help=helpMessagePool["version"])
	optionalArg.add_argument('-h', '--help', action='help',
				default=argparse.SUPPRESS,
				help=helpMessagePool["help"])

	def checkFilters(store, lang, pricemin, pricemax):
		# sanity check of passed arguments
		global allstores
		if store is None:
			print("enter store's country code")
			sys.exit()
		correctStore = allstores[lang]
		try:
			correctStore.index(store)
		except ValueError:
			print("can't combine store language '{}' with store country code '{}'".format(lang, store))
			sys.exit()
		if 0 > pricemin or pricemin > pricemax or \
			(pricemin > pricemax and pricemax != parser.get_default('max')):
			print("a dealmaker? more like a dealbreaker with that price")
			sys.exit()

	def sortdata(data, sortingList, reverse=False):
		"""Return a string message of applied sorting."""
		message = "sorted by {}".format(" then by ".join(sortingList))
		if reverse: message += " in reverse"
		sortingHat = {"price": "roundprice", "title": "name", "discount": "discount"}
		sortingList = [sortingHat[i] for i in sortingList]
		data.sort(key=itemgetter(*sortingList), reverse=reverse)
		return message

	def fullShebang(printQuery=False, printDeal=False, newline=False):
		global lang, store, pages, deal, data, querySwitch, \
			lenPair, tableprint, minprice, maxprice, \
			sortingList, sortReverse
		messagePool = []
		sortMessage = None
		if sortingList:
			noDupes = []
			[noDupes.append(i) for i in sortingList if i not in noDupes]
			sortMessage = sortdata(data, noDupes, sortReverse)
		priceRange = "price range: "
		if minprice != parser.get_default('min'):
			priceRange += "from {} ".format(minprice)
		if maxprice != parser.get_default('max'):
			priceRange += "under {}".format(maxprice)
		if len(priceRange) == 13:
			priceRange = None

		# get messages (filenames) from write functions
		today = time.strftime("%Y %b %d")
		savedMessage = [
			func(data, deal, lang, store, genDate=today, msort=sortMessage, prange=priceRange, query=querySwitch)
			for func in (writereddit, writehtml) if func
		]
		if writetext:
			savedMessageTxt = \
				writetext(
					data, deal=deal, genDate=today,
					tlen=lenPair[0], plen=lenPair[1],
					lang=lang, store=store, table=tableprint,
					msort=sortMessage, prange=priceRange, query=querySwitch
				)
			messagePool.append(savedMessageTxt)

		if not noprint:
			if newline: print()
			printitems(data, tlen=lenPair[0], plen=lenPair[1], table=tableprint)
		if printDeal:
			printMessage = "fetched {} items from the '{}' deal. pages: {}"
			printMessage = printMessage.format(len(data), deal, pages)
		elif printQuery:
			printMessage = "found {} items for '{}' query. page 1 results only"
			printMessage = printMessage.format(len(data), deal)
		if sortMessage: printMessage += ". " + sortMessage
		print(printMessage)
		[messagePool.append(m) for m in (savedMessage) if savedMessage != []]
		if writereddit == writehtml == writetext is None and noprint:
			print(randomNothing(mtype=1))
		if messagePool != []:
			return messagePool

	args = parser.parse_args()
	store = args.store
	lang = args.lang
	getAll = args.alldeals
	queryPhrase = args.query
	sortingList = args.sort
	sortReverse = args.reverse
	minprice = args.min
	maxprice = args.max
	tableprint = args.table
	noprint = args.noprint
	writetext = args.writetext
	writereddit = args.writereddit
	writehtml = args.writehtml

	if args.storelist:
		storelist()
		sys.exit()

	try:
		checkFilters(store, lang, minprice, maxprice)
		if queryPhrase:
			deal = query = " ".join(queryPhrase)
			querySwitch = True
			pages = 1
			data, lenPair = searchitems(query, lang, store, minprice=minprice, maxprice=maxprice)
			if data != []:
				messagePool = fullShebang(printQuery=True)
				if messagePool is not None:
					print("saved output: \n - {}".format("\n - ".join(messagePool)))
				sys.exit()
			else:
				print(randomNothing(), "try another query.")
		else:
			deals = getdeals(lang, store, fetchall=getAll)
			querySwitch = False
			messagePool = []
			p = multiprocessing.Pool(processes=multiprocessing.cpu_count())
			for deal, dealurl in deals:
				pages = itercount(deal, dealurl)
				if pages:
					datalists = p.starmap_async(
							getitems, zip(
								repeat(dealurl), range(1, pages + 1),
								repeat(minprice), repeat(maxprice)
								)
							).get()
					if datalists[0][0] != []:
						data = []
						lenPairs = []
						for itemlist, lenPair in datalists:
							data.extend(itemlist)
							if lenPair != []:
								lenPairs.extend([lenPair])
						datalists.clear()
						data = list(unique_everseen(data))
						lenPair = [max(i) for i in zip(*lenPairs)]
						if len(deals) > 1:
							messagePoolIncomplete = fullShebang(printDeal=True, newline=True)
						else:
							messagePoolIncomplete = fullShebang(printDeal=True)
						if messagePoolIncomplete is not None:
							messagePool += messagePoolIncomplete
					else:
						print("deal: {}. reply: {}".format(deal, randomNothing()), end=" ")
						if minprice or maxprice:
							print("try retweaking those filters")
			if messagePool != []:
				print("saved output: \n - {}".format("\n - ".join(messagePool)))
			p.close()
			p.join()
	except KeyboardInterrupt:
		print()
		sys.exit()
