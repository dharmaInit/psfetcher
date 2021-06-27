from modules.globals import PREFERENCES_CONFIG


def printExamples():
	"""Return None. Print some psfetcher command examples."""

	examples = """	DEALS:

	plain deal fetching:
	  psfetcher -s us

	fetch every deal without entering the prompt:
	  psfetcher -s cz -a

	fetch every deal, show only games and save results to an HTML document:
	  psfetcher -s gb -aw --type game

	fetch every deal, select only addons and save results to a text file without printing them to the terminal:
	  psfetcher -s hu -atn --type addon

	initiate deal fetching, sort results by title and show games only:
	  psfetcher -s at -l de --sort title --type game

	initiate deal fetching, ignore results from the previous run and fetch anew, and show addons only:
	  psfetcher -s at -l de --type addon -i

	initiate deal fetching, sort results by price in reverse and show addons only:
	  psfetcher -s es -l es --sort price --type addon --reverse

	initiate deal fetching, show only games starting from 10 EUR but under 25:
	  psfetcher -s it -l it --type game -f 10 -u 25
	-------------------------------------------------------------------------------------------------------------

	SEARCH:

	initiate a search:
	 psfetcher -s dk -l da -q the last of us, sekiro

	initiate a search, sort results by price then by discount:
	 psfetcher -s be -l fr -q mafia --sort price discount

	initiate a search, show games only and print results like a table:
	 psfetcher -s fi -l fi -q metal gear --type game --table

	initiate a search, don't print the results but save them to an XLSX spreadsheet:
	 psfetcher -s pl -l pl -q god of war -nx
	-------------------------------------------------------------------------------------------------------------

	WATCHLIST:

	add a title:
	 psfetcher -s us watchlist --add horizon zero dawn

	add the same title, different store:
	 psfetcher -s gb watchlist --add horizon zero dawn

	check prices, sort results by title (locked to the current store):
	 psfetcher --sort title -s us watchlist --check

	show all titles in the watchlist (all stores):
	 psfetcher -s us watchlist --show

	remove a title (all stores):
	 psfetcher -s us watchlist --remove
	-------------------------------------------------------------------------------------------------------------
	"""

	advice = """
	most of these arguments and options can be set in\n	{}
	""".format(PREFERENCES_CONFIG)
	print(examples, advice)
