# Change Log

## [1.1.0] - 2021-06-27

New features demanded for the script to be broken into multiple sub-modules.

The main script is still psfetcher.py. Sub-modules are located in the 'modules' directory.

### Added
- new commands: watchlist, flush, flushall, preferences, examples
- new settings for custom preferences in 'preferences.json'
- new file 'preferences.json.example'
- new column in the output and in the database: 'platform'
- new function itemPrice: fetches a single item's information

### Changed
- the '--list' option moved to 'list' (as a command)
- columns in the database: dealid > dealID, titleid > titleID
- main help page formatting
- the generation date is no longer shown in output files
- moved configuration files to 'conf' directory
- moved the database file to 'db' directory
- moved the script's 'engine' to the main function

### Fixed


## [pre 1.1.0] - 2020-2021

Script wasn't complex enough to warrant a changelog. Mostly bug fixes and API adaptations were implemented.

Notable changes came with version 1.0.4: querying multiple titles at a time and SQLite introduction.
