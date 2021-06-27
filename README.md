 # psfetcher
 Fetch deals or search for game titles in PS Store

 # Features:
  - fetch deals
  - search for game titles
  - multi-store support
  - watchlist - custom list of picked titles
  - sort results by title, price, or discount
  - filter results by setting minimum and/or maximum prices
  - filter results by content type - games and/or addons
  - save results as a text file, a reddit-friendly comment, an HTML document, or an XLSX spreadsheet

 # Installation and requirements
 Required Python version is 3+. External libraries need to be installed manually:

 `pip install -r requirements.txt`

 # Usage and information:

 Script is not based on any API, so any site changes might cause it to break.

 To initiate either a deal-fetching process or a search, 2 arguments are needed.

 Both arguments are taken from https://store.playstation.com/yy-xx/, where yy is a language code, and xx is a country code.

 Pass the language code to `-l / --lang` and the country code to `-s / --store`.

 By default `-l / --lang` is set to 'en', meaning English, however not all stores support it. Use the `list` command to list possible combinations.
 
 To entirely skip `-l` and `-s` parameters, set both codes in `preferences.json` (more on this in [Preferences](#preferences)).

   ## Deals:
   To get the results of a single deal, enter its index in the interactive mode that will list all deals. To choose more than one deal, separate indexes by space.

   To get all current deals, pass the `-a / --alldeals` option to skip the prompt.

   If a deal has a single item, it will be skipped.

    To list all available deals, a single request is sent to https://store.playstation.com/yy-xx/deals.
    While fetching specific deal's results, multiple parallel processes, specifically number of the machine's CPUs,
    crawl through the deal's pages to download titles and prices.
    However, if more than one deal is chosen, one at a time will be worked on.
    
   ## Search:
   To search for a game title, pass the argument to `-q / --query`.

   - title can be wrapped in quotes or be without them
   - multiple titles should be separated by a comma
   - the query is case-insensitive, however, the queried phrase should be present completely in that order in a possible match
   - to get better results, use a game's title without "x edition", "dlc", etc., as they will likely be included
   - the fetched results are from the first page only, as they're the most relevant.
     subsequent pages mostly contain items having separate words from the query as their title
     
  ## Watchlist:
  The `watchlist` command has 4 main options: `--add`, `--show`, `--check`, and `--remove`.
  
   - `--add` takes one argument - game's title - that will be searched for in PS Store and added to the watchlist
     - a title is not added automatically: its index must be entered in the prompt
     - separate indexes by space if there's more than one
   - `--show` prints all current watchlist titles from all stores
   - `--check` checks prices of watchlist titles tied to the current store
     - if identical titles are added to multiple stores, change the store to check their prices
   - `--remove` prints all current watchlist titles from all stores and removes them by their indexes
     - separate indexes by space if there's more than one
    
  Filters, arguments and other options must precede `watchlist` in the command.

   ## Filters:
   To narrow results by content type, pass 'game' and/or 'addon' to `--type`. Virtual currency has its own category, 'currency'.
   
    What is considered as a 'game':
     ['Full Game, Game Bundle, Premium Edition, Bundle, Demo']
    What is considered as an 'addon':
     ['Add-On Pack, Add-on, Character, Level, Vehicle, Map, Costume, Item, Season Pass']
  
   To narrow results by a custom price range, pass a natural number that denotes a local currency's value to `-f / --from` and/or `-u / --under`.

    Might not work as intended in some stores, as a decimal separator's placement differs depending on a country's standards.
    An attempt is made to fix this issue. This applies to sorting by price as well, read below.

   ## Sorting:
   - results can be sorted by either price, title, or discount value. More than one sorting level can be used. Pass them to `--sort` only once.
   For example, to sort by price then by title, use `--sort price title`, and not `--sort price --sort title` (the latter will sort only by title)
   - to reverse the order of sorting, use `--reverse`.

   ## Output operations:
   By default, results are printed to the terminal. To disable this, use `-n / --noprint` option.

   To alter the default printed format to table-like format, use `--table`.
   ### Saving output:
   - `-t / --text`, to save results as a text file
      - table-like format can be applied here as well
   - `-r / --reddit`, to save results as a reddit-friendly comment
      - automatic split into multiple comments before reaching character limit (10000)
   - `-w / --web`, to save results as a simple HTML document
   - `-x / --xlsx`, to save results as an XLSX spreadsheet

   A Reddit comment, an HTML document and an XLSX spreadsheet will contain direct store links while a plain text file will not.

  ## Commands:
  `examples` prints out to the terminal some psfetcher command examples
  
  `flush` removes everything from the database (for all stores), leaving only watchlist titles
  
  `flushall` removes everything from the database (for all stores)
  
  `preferences` prints current preferences set in `preferences.json` in a human-readable format
  
  ## Preferences:
   Most of the main arguments and options can be set in `preferences.json`. Formatting and example can be found in `preferences.json.example`.
   

  ## Misc 
   PS Store no longer shows deals' written names on https://store.playstation.com/yy-xx/deals. However, names are still present in site code and they are mostly the same for all stores (except for the "All Deals" deal, which is often translated to a store's language). "Games Under x" type of deals have one confusing bit - the x's currency is mostly USD, even if a store's currency is different.
   
 All fetched data is saved to a local SQLite database. If a deal is queried multiple times and the deal is still active, old data from the previous run will be used (applicable to deals only; search and `watchlist --check` results are new). To ignore old data and fetch everything again, use `-i / --ignore` option.
 
 PS Store rehashes old URLs which are used as deal IDs in the script, which means that old results from an inactive deal could be shown. It is advised to remove old data from the database using the `flush` command if a deal is no longer active to avoid inconsistencies. 

 Not all titles have a platform specified in their tags. Such cases are noted under the platform column as "PS".
 
   ### What's in thoughts but not in the works:
   - adding OpenCritic to the HTML version of the output (needs OC's agreement)
