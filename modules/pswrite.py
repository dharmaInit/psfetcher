import openpyxl


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
	dlen = len("Discount")
	header = "{} | {} | {} | {}\n".format(
		"Title".ljust(tlen), "Price".ljust(plen),
		"Discount".ljust(dlen), "Platform"
	)
	with open(filename, "w") as output:
		output.write("{}\n".format(filterMessage))
		output.write(header)
		for item in itemlist:
			if table:
				output.write("-" * round(len(header)) + "\n")
			itemline = "{} | {} | {} | {}\n".format(
				item["title"].ljust(tlen),
				item["price"].ljust(plen),
				item["discount"].ljust(dlen),
				item["platform"])
			output.write(itemline)
	return filename


def writereddit(itemlist=None, lang=None, country=None, filename=None, filterMessage=None):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts)
	lang (str): 2-letter language code
	country (str): 2-letter country code
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	"""
	header = "Title | Price | Discount | Platform\n---|---|---|----"
	filterMessage = filterMessage + "\n"
	commentLen = len(header + filterMessage)
	with open(filename, "w") as output:
		output.write("{}\n".format(filterMessage))
		output.write(header)
		for item in itemlist:
			itemline = "\n[{}]({}) | {} | {} | {}".format(
				item["title"],
				"https://store.playstation.com/{}-{}/product/".format(lang, country) + item["titleID"],
				item["price"],
				item["discount"],
				item["platform"])
			output.write(itemline)
			commentLen += len(itemline)
			if commentLen > 9800:
				commentLen = len(header)
				output.write("\n\n{}".format(header))
	return filename


def writehtml(itemlist=None, lang=None, country=None, filename=None, filterMessage=None, deal=None):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts)
	lang (str): 2-letter language code
	country (str): 2-letter country code
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	deal (str): deal's name
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
		"\n</style>" % deal.upper()
	)
	heading = "\n<h2>{} ({}-{} STORE)</h2>".format(deal.upper(), lang.upper(), country.upper())
	lowerHeading = "\n<h3>{}</h3>".format(filterMessage)
	tableHeader = (
		"\n<table>"
		"\n\t<tr>\n\t\t<th>Title</th>"
		"\n\t\t<th>Price</th>"
		"\n\t\t<th>Discount</th>"
		"\n\t\t<th>Platform</th>"
		"\n\t</tr>"
	)
	productUrl = "https://store.playstation.com/{}-{}/product/".format(lang, country)
	tRow = (
		"\n\t<tr>\n\t\t<th>"
		"<a href=\"{}{}\">{}</a></th>"
		"\n\t\t<th>{}</th>\n\t\t<th>{}</th>\n\t\t<th>{}</th>\n\t</tr>"
	)
	footer = "\n</table>\n</body>\n</html>"
	with open(filename, "w") as output:
		[output.write(i) for i in (header, heading, lowerHeading, tableHeader)]
		for item in itemlist:
			output.write(tRow.format(
				productUrl, item["titleID"], item["title"],
				item["price"],
				item["discount"], item["platform"]
				)
			)
		output.write(footer)
	return filename


def writexlsx(itemlist=None, lang=None, country=None, filename=None, filterMessage=None, deal=None):
	"""Return filename of a file to which all output has been saved.

	Parameters:
	itemlist (list): data list of items (dicts) returned from getitems()
	lang (str): 2-letter language code
	country (str): 2-letter country code
	filename (str): save output to 'filename'
	filterMessage (str): a message of applied filters
	deal (str): deal's name
	"""
	wb = openpyxl.Workbook()
	sheet = wb.active
	sheet.title = deal
	sheet["A1"] = filterMessage
	sheet["A2"] = "Title"
	sheet["B2"] = "Price"
	sheet["C2"] = "Discount"
	sheet["D2"] = "Link"
	sheet["E2"] = "Platform"
	productUrl = "https://store.playstation.com/{}-{}/product/".format(lang, country)
	for ind, item in enumerate(itemlist):
		ind += 3
		url = productUrl + item["titleID"]
		cells = {"A": item["title"], "B": item["price"], "C": item["discount"], "D": url, "E": item["platform"]}
		for cell, data in cells.items():
			sheet[cell + str(ind)] = data
	wb.save(filename)
	return filename
