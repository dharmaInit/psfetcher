import os

WORKDIR = os.path.dirname(os.path.realpath(__file__))
WORKDIR = os.path.dirname(WORKDIR)
DBFILE = os.path.join(WORKDIR, "db/psfetcher.db")
CONFIG = os.path.join(WORKDIR, "conf/lang.json")
PREFERENCES_CONFIG = os.path.join(WORKDIR, "conf/preferences.json")

MINPRICE = 0
MAXPRICE = 100000
