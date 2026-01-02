This doc goes over the things you'll want ot make sure and do if there is a ew data source added.    Relatively short and sweet, luckily!

Last updated: 11/25/2025

- **Loader:** You'll naturally want to make a loader, whether this is nflreadpy, some other repo, or whatever else.  However, you'll need to add that to the script which loads all data.
- **Schema Check:** The schema in DuckDB autogenerates based on path, so think about where you're going to put it.  Make sure that it's being properly loaded to the database formed.  That does mean firing up Harlequin and making sure your data works there.
- **yamplayer_id Injection:**  There's a script which generates and injects a universal, unique player ID to make joining easy across data sources.  You'll need to make sure your data is added there.
- **Indexes:**  Add the set to the indexing script with desired indexes
- **Runner:** Make a script runner
  - This might include a script as well as adding in the toml file
  - Will need to add to help/list command as well
- **Checks**
  - Make sure you check any other main scripts or tasks.
  - Any other universal ID's