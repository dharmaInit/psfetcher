import json
import os

from modules.globals import CONFIG, PREFERENCES_CONFIG, MINPRICE, MAXPRICE


def getConf():
	"""Return two dictionaries containing configurations.

	The configuration is parsed from a JSON file, CONFIG.
	If CONFIG cannot be read or doesn't exist, return None, None.

	The first dict, allstores, contains language codes as keys.
	Each value is a list containing country codes related the language code.

	The second dict, allcontent, contains language codes as keys.
	Each value is a nested dict with 3 keys used for content filtering: addon, game, and currency.
	Each value of a sub-key is a list containing language-specific translations of the content type (sub-key).
	"""
	if not os.path.isfile(CONFIG) or not os.access(CONFIG, os.R_OK):
		print("ensure you have '{}' with at least read access".format(CONFIG))
		return None, None

	allstores = {}
	allcontent = {}
	with open(CONFIG, "r") as conf:
		conf = json.load(conf)
		for lang in conf.keys():
			allstores[lang] = conf[lang]["country"]
			allcontent[lang] = conf[lang]["content"]
		return allstores, allcontent


def getPrefConf():
	"""Return a dictionary containing user-set configuration.

	The configuration is parsed from a JSON file, PREFERENCES_CONFIG.
	If PREFERENCES_CONFIG cannot be read or doesn't exist, return a dict with empty configuration.
	"""
	if os.path.isfile(PREFERENCES_CONFIG) and os.access(PREFERENCES_CONFIG, os.R_OK):
		with open(PREFERENCES_CONFIG, "r") as config:
			return json.load(config)

	prefconf = {}
	prefconf["minprice"] = MINPRICE
	prefconf["maxprice"] = MAXPRICE
	prefconf["language"] = prefconf["country"] = None
	prefconf["content"] = prefconf["sorting"] = []
	keys = [
		"saveTXT", "saveHTML", "saveRDT", "saveXLSX",
		"sortReverse", "getAllDeals", "ignorePreviousFetch",
		"tablePrint", "dontPrint",
	]
	for key in keys:
		prefconf[key] = False
	return prefconf


def checkPreferences():
	"""Return None.

	Print all user-set configuration in a human-readable format from a dict returned by getPrefConf.
	"""
	prefconf = getPrefConf()
	prefs = {
		"language": prefconf["language"],
		"country": prefconf["country"],
		"minimum price": prefconf["minprice"],
		"maximum price": prefconf["maxprice"],
		"content type": " and ".join(prefconf["content"]),
		"sorting order": " then ".join(prefconf["sorting"]),
		"sorting is reversed": prefconf["sortReverse"],
		"fetch all deals": prefconf["getAllDeals"],
		"print results in table-like format": prefconf["tablePrint"],
		"don't print results to the terminal": prefconf["dontPrint"],
		"ignore previous fetch and fetch anew": prefconf["ignorePreviousFetch"],
		"save results as a text file": prefconf["saveTXT"],
		"save results as an HTML document": prefconf["saveHTML"],
		"save results as a reddit comment": prefconf["saveRDT"],
		"save results as an XLSX spreadsheet": prefconf["saveXLSX"]
	}

	for setting, value in prefs.items():
		print(" {}: {}".format(setting, str(value).lower()))
