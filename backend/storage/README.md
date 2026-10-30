# Storage

Runtime data. The gateway writes its SQLite audit database here by default (`sentinel.db`, git-ignored). In Docker the
database lives on the `sentinel-data` volume (`/data/sentinel.db`). Set `SENTINEL_DB_PATH` to change it.
