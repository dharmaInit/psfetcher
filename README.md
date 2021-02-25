 # psfetcher
 Fetch deals or search for game titles in a PS Store

 # Features:
  - fetch deals
  - search for a game title
  - multi-store support
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

 By default `-l / --lang` is set to 'en', meaning English; however, not all stores support it. To see which language code goes with which country code, use `--list`.

   ## Deals:
   To get results of a single deal, enter its index in the interactive mode that will list all deals. To choose more than one deal, separate indexes by space.

   To get all current deals, pass the `-a / --alldeals` option to skip the prompt.

   If a deal has a single item, it will be skipped.

    To list all available deals, a single request is sent to https://store.playstation.com/yy-xx/deals.
    While fetching specific deal's results, multiple parallel processes, specifically number of the machine's CPUs,
    crawl through the deal's pages to download titles and prices.
    However, if more than one deal is chosen, one at a time will be downloaded,
    but as mentioned before, each specific deal spawns multiple processes to download data.

   ## Search:
   To search for a game title, pass the argument to `-q / --query`.

   - title can be wrapped in quotes or be without them
   - only one title at a time can be queried
   - the query is case-insensitive; however, the queried phrase should be present completely in that order in a possible match
   - to get better results, use a game's title without "x edition", "dlc", etc., as they will likely be included
     - e.g., if the game's title is "The Horror of Fetcher: 2020 Game of the Year Edition",
       and the query is "the horror of fetcher game of the year edition", it will yield no result. "the horror of fetcher" will suffice
   - the only fetched results are from the first page, as they're most relevant. 
    subsequent pages mostly contain items having separate words from the query as their title

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
   - to reverse the order of sorting, use `--reverse`

   ## Output operations:
   By default, results are printed on the terminal. To disable this, use `-n / --noprint` option.

   To alter the default printed format to table-like format, use `--table`.
   ### Saving output:
   - `-t / --text`, to save results as a text file
      - table-like format can be applied here as well
   - `-r / --reddit`, to save results as a reddit-friendly comment
      - automatic split into multiple comments before reaching character limit (10000)
   - `-w / --web`, to save results as a simple HTML document
   - `-x / --xlsx`, to save results as an XLSX spreadsheet

   A Reddit comment, an HTML document and an XLSX spreadsheet will contain direct store links while a plain text file will not.

  ## Misc 
   PS Store no longer shows deals' written names on https://store.playstation.com/yy-xx/deals. However, names are still present in site code and they are mostly the same for all stores (except for the "All Deals" deal, which is often translated to a store's language). "Games Under x" type of deals are not translated and are generally the same with one confusing bit - the x's currency is USD, even if a store's currency is different.
   
   Some titles from a deal can be present more than one time - they are filtered out.
   
   Fetching the same deal at different times can yield slightly different results. Any deal has been observed to have a fixed number of titles, however, due to some titles being present more than one time, some unique titles are left out. For example, a deal has 5 items. Included items are: 1, 2, 3, 4, 4. 5 is left out. So the end, unique result is 1, 2, 3, 4. But on subsequent attempts item '5' can pop up in the deal, something else might be dropped, or everything can be unique. This conclusion might not be entirely accurate.

   ### What's in thoughts but not in the works:
   - a GUI version
   - ~~separation by content type (games vs DLCs). Requires an external database for filtering results, as that option got removed with the revamp of PS Store~~
      - done as of version 1.0.3
   - separation by platform (PS4 and PS5). Not useful as of now, as PS5 titles are currently at the minimum
      - written but not implemented due to the reason above