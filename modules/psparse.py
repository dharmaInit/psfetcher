import argparse
import re

from modules import pswrite
from modules.psconfig import getPrefConf
from modules.version import __version__


def getVars():
	"""Return all parsed variables from argparse.

	Sets default values according to a user-set configuration from getPrefConf, if it's present.
	"""

	# argparse's internal tweaking for a better help page
	class CustomFormatter(argparse.HelpFormatter):
		def _format_action(self, action):
			parts = super(CustomFormatter, self)._format_action(action)
			if action.nargs == argparse.PARSER:
				parts = "\n".join(parts.split("\n")[1:])
			return parts

		def _format_action_invocation(self, action):
			if not action.option_strings:
				metavar, = self._metavar_formatter(action, action.dest)(1)
				return metavar
			else:
				parts = []
				if action.nargs == 0:
					parts.extend(action.option_strings)
				else:
					default = action.dest.upper()
					args_string = self._format_args(action, default)
					if "{" in args_string:
						dup_remove_reg = re.compile(r"\{[A-Za-z, ]+\}\s")
						args_string = dup_remove_reg.search(args_string).group()
					for option_string in action.option_strings:
						parts.append(option_string)
					parts[-1] += " " + args_string
				return ", ".join(parts)

	prefconf = getPrefConf()
	parser = argparse.ArgumentParser(
			prog="psfetcher",
			description="Fetch deals or search for game titles in PS Store",
			usage="%(prog)s -s xx [option]", add_help=False,
			formatter_class=CustomFormatter)
	requiredArg = parser.add_argument_group("required arguments")
	optionalArg = parser.add_argument_group("optional arguments")
	flagsArg = parser.add_argument_group("options")
	requiredArg.add_argument(
		"-s", "--store", metavar="xx", default=prefconf["country"],
		type=str, help="2-letter country code"
	)
	requiredArg.add_argument(
		"-l", "--lang", metavar="xx",
		type=str, default=prefconf["language"],
		help="2-letter language code"
	)
	optionalArg.add_argument(
		"-f", "--from", dest="min", metavar="N",
		default=prefconf["minprice"],
		type=int, help="title's minimum price"
	)
	optionalArg.add_argument(
		"-u", "--under", dest="max", metavar="N",
		default=prefconf["maxprice"],
		type=int, help="title's maximum price"
	)
	optionalArg.add_argument(
		"--type", nargs='+',
		default=prefconf["content"],
		choices=["game", "addon", "currency"],
		help="show only specific content types"
	)
	optionalArg.add_argument(
		"--sort", nargs='+',
		default=prefconf["sorting"],
		choices=["price", "title", "discount"],
		help="sort results by price, title, or discount"
	)
	optionalArg.add_argument(
		"-q", "--query", metavar=("title", "title2"), type=str, nargs="+",
		help="search for a title (page 1 results only)"
	)
	flagsArg.add_argument(
		"-a", "--alldeals", action="store_true",
		default=prefconf["getAllDeals"],
		help="select all available deals"
	)
	flagsArg.add_argument(
		"-i", "--ignore", action="store_true",
		default=prefconf["ignorePreviousFetch"],
		help="ignore results from the previous run"
	)
	flagsArg.add_argument(
		"-t", "--txt", action="store_true", dest="writetext",
		default=prefconf["saveTXT"], help="save results as a text file"
	)
	flagsArg.add_argument(
		"-r", "--reddit", action="store_true", dest="writereddit",
		default=prefconf["saveRDT"], help="save results as a reddit-friendly comment"
	)
	flagsArg.add_argument(
		"-w", "--web", action="store_true", dest="writehtml",
		default=prefconf["saveHTML"], help="save results as an HTML document"
	)
	flagsArg.add_argument(
		"-x", "--xlsx", action="store_true", dest="writexlsx",
		default=prefconf["saveXLSX"], help="save results as an XLSX spreadsheet"
	)
	flagsArg.add_argument(
		"-n", "--noprint", action="store_true",
		default=prefconf["dontPrint"],
		help="don't print the results"
	)
	flagsArg.add_argument(
		"--table", action="store_true",
		default=prefconf["tablePrint"],
		help="table-like printed/saved results"
	)
	flagsArg.add_argument(
		"--reverse", action="store_true",
		default=prefconf["sortReverse"],
		help="reversed --sort results"
	)
	flagsArg.add_argument(
		"-v", "--version", action="version",
		version="%(prog)s {}".format(__version__),
		help="show script's version and exit"
	)
	flagsArg.add_argument(
		"-h", "--help", action="help",
		default=argparse.SUPPRESS,
		help="show this help message and exit"
	)
	del prefconf

	subparsers = parser.add_subparsers(title="commands", dest="command")

	# watchlist help page
	watchlistHelpGeneral = "options:\n"
	watchlistHelpGeneral += "  --show\t\tshow titles\n"
	watchlistHelpGeneral += "  --check\t\tcheck prices\n"
	watchlistHelpGeneral += "  --add [title]\t\tsearch and add a title\n"
	watchlistHelpGeneral += "  --remove\t\tremove a title\n\n"
	watchlistEpilog = "--show and --remove are store-independent.\n"
	watchlistEpilog += "--check and --add are tied to the current store.\n"
	watchlistEpilog += "Main arguments and options must precede 'watchlist' in the command.\n"
	watchlistArg = subparsers.add_parser(
		"watchlist", usage="%(prog)s -h", help="custom list of picked titles", description=watchlistHelpGeneral,
		formatter_class=argparse.RawTextHelpFormatter, add_help=False,
		epilog=watchlistEpilog
	)
	watchlistArg.add_argument(
		"--show", dest="subCommand", const="show",
		action="store_const", help=argparse.SUPPRESS
	)
	watchlistArg.add_argument(
		"--check", dest="subCommand", const="check",
		action="store_const", help=argparse.SUPPRESS
	)
	watchlistArg.add_argument(
		"--add", dest="subCommand",
		nargs="*", help=argparse.SUPPRESS
	)
	watchlistArg.add_argument(
		"--remove", dest="subCommand", const="remove",
		action="store_const", help=argparse.SUPPRESS
	)
	watchlistArg.add_argument(
		"-h", "--help", action="help",
		default=argparse.SUPPRESS, help=argparse.SUPPRESS
	)

	listArg = subparsers.add_parser("list", help="list all language and country codes", add_help=False)
	listArg.add_argument(const="list", action='store_const', dest="command")

	flushArg = subparsers.add_parser("flush", help="remove everything from db except for watchlist titles")
	flushArg.add_argument(const="flush", action='store_const', dest="command")

	flushAllArg = subparsers.add_parser("flushall", help="remove everything from db", add_help=False)
	flushAllArg.add_argument(const="flushall", action='store_const', dest="command")

	preferencesArg = subparsers.add_parser("preferences", help="show current preferences", add_help=False)
	preferencesArg.add_argument(const="preferences", action='store_const', dest="command")

	examplesArg = subparsers.add_parser("examples", help="show some examples", add_help=False)
	examplesArg.add_argument(const="examples", action='store_const', dest="command")

	args = parser.parse_args()
	country = args.store
	lang = args.lang
	argCommand = args.command
	argQuery = args.query
	argSortingList = args.sort
	argContentTypes = args.type
	minprice = args.min
	maxprice = args.max
	printTableResults = args.table
	dontPrintResults = args.noprint
	ignorePreviousFetch = args.ignore
	reverseResults = args.reverse
	getAllDeals = args.alldeals

	writetext = args.writetext
	if writetext:
		writetext = pswrite.writetext
	writereddit = args.writereddit
	if writereddit:
		writereddit = pswrite.writereddit
	writehtml = args.writehtml
	if writehtml:
		writehtml = pswrite.writehtml
	writexlsx = args.writexlsx
	if writexlsx:
		writexlsx = pswrite.writexlsx

	operation = "FETCHDEAL"
	if argQuery:
		operation = "FETCHITEM"

	subCommand = addTitle = None
	if argCommand == "watchlist":
		if not args.subCommand:
			watchlistArg.print_usage()
		else:
			if type(args.subCommand) is list:
				subCommand = "add"
				addTitle = " ".join(args.subCommand)
			else:
				subCommand = args.subCommand
		operation = "WATCHDOG"

	return country, lang, argCommand, subCommand, addTitle, \
		argQuery, argSortingList, argContentTypes, minprice, maxprice, \
		printTableResults, dontPrintResults, ignorePreviousFetch, \
		reverseResults, getAllDeals, \
		writetext, writereddit, writehtml, writexlsx, operation
