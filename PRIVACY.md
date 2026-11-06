# Privacy

This project is built for material that belongs to one person. Treat the
database as a private file, not as a normal application cache.

## What stays local

`twin.py` has no network code. It does not upload, sync, call an API, or send
telemetry. All records and metrics stay in the SQLite database you point it at,
by default `.twin/twin.db`.

The `draft` command prints a persona prompt that contains retrieved evidence.
That output is as sensitive as the records it quotes. If you paste it into a
cloud model or a chat window, the evidence leaves your machine at that point.
The tool cannot control what happens after you copy its output.

## Privacy levels

- `public`: safe to publish.
- `private`: personal material used for local retrieval.
- `restricted`: sensitive material that is excluded from the default scope.

`draft` defaults to the `private` scope, which means `public` plus `private`.
`restricted` records are only retrieved with `--scope all`.

The scope filter is applied in SQL before results are returned. This is a
retrieval control, not encryption. Anyone with the database file can read all
levels. Use full-disk encryption and operating-system file permissions when the
corpus is sensitive.

## What to commit

Do not commit:

- `.twin/` or any `.db`, `.sqlite`, or `.sqlite3` file
- raw exports, message archives, transcripts, or audio
- anything that identifies another person without their consent
- prompts that quote private evidence

The included `demo/` corpus is synthetic. It describes a fictional person and
contains no real messages.

## Deletion

There is no delete command in v0.1. To remove all data, delete the database
directory (`.twin/` by default) and any copies or backups you made. If the
database was on a synced drive, check the sync service's version history too.

## Before publishing derived work

A style fingerprint or persona prompt can still reveal private facts even when
it contains no verbatim quote. Review any output before sharing it. For a public
demo, use synthetic records or records you wrote specifically for publication.
