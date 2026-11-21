# Operations: backup, restore and moving projects

What to keep, how to keep it, and how to bring it back, for each way CivilLabPro OS runs.

## What holds your data

| Installation | Data | Where |
|---|---|---|
| Desktop app | one SQLite file, with its write-ahead log | `civillabpro.db` (and `-wal`, `-shm`) in the data folder: Windows `%APPDATA%\CivilLabPro OS`, Linux `~/.config/CivilLabPro OS` |
| Small server, single process | one SQLite file | the path in `CLP_DATABASE_URL` |
| Server | PostgreSQL 16 | the database in `CLP_DATABASE_URL` |

The signing key (`CLP_JWT_SECRET`; on the desktop, `secret.key` in the data folder) only signs sessions. Losing it signs everyone out and loses no data.

## Back up

**Desktop app or a single-organisation SQLite server.**

1. The organisation's owner opens **Data and backup** (sidebar; on the desktop also File, Back up data) and chooses **Download a backup**.
2. The server writes a consistent copy with SQLite's `VACUUM INTO` while it keeps running, and the browser saves it as `civillabpro-backup-<date>.db`.
3. Keep copies somewhere other than the computer they came from.

The button refuses a database that holds more than one organisation, so that no owner can download another tenant's data. Such a server is backed up as a whole at the server.

**SQLite server, by hand.** Stop the service and copy the file with its `-wal` and `-shm` files. Or, with it running, run `sqlite3 <file> "VACUUM INTO '<backup>.db'"`.

**PostgreSQL server.**

```bash
pg_dump --format=custom --file=civillabpro-$(date +%F).dump "$DATABASE_URL"
```

Schedule it (cron, or the platform's own backups) and keep the dumps off the server.

## Restore

**Desktop app.**

1. Choose File, **Restore from backup**, and pick a `.db` backup.
2. The app stops its server, keeps the current data in the data folder as `civillabpro.before-restore-<date>.db`, puts the backup in its place and starts again.
3. A backup from an older version is brought up to date by the migrations on start. If the backup cannot be opened, the previous data is put back and the app says so.
4. Sign in again afterwards.

To undo a restore, restore the kept `before-restore` file the same way.

**SQLite server.** Stop the service, replace the file (and remove its `-wal` and `-shm`), then start it. `python -m app.serve` migrates before serving.

**PostgreSQL server.**

```bash
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" civillabpro-2026-11-20.dump
alembic upgrade head        # if the dump is from an older version
```

## Move a project between installations

From desktop to the office server, between colleagues, or from one organisation to another:

1. On the project's page choose **Export project**. That saves one `.clp.json` file with the project, every design, each design's revision history and its review record, and the project's estimates.
2. On the other installation choose **Import project** (on the Projects page, or on Data and backup) and pick the file.

The import:

* creates a new project in your organisation;
* brings the designs in as they were calculated, with the engine version that made them, and does not recalculate them (a revision recalculates as usual);
* brings the estimates in as drafts or issued as they were, their quantities still linked to the same designs (now the imported ones); schedules of rates and rate analyses are the organisation's, not the project's, and do not travel (an estimate keeps its rates);
* reads files of format version 1 (before estimates) and 2;
* gives the project a suffixed job number (`-2`, `-3`) if its own is already in use, and says so;
* refuses a file with an element this installation does not have (update it first), or with a design whose result disagrees with its own record (a damaged file);
* records the source organisation, exporter and date in the audit trail.

The file is not signed. The check catches damage and careless edits, not a deliberate forgery, so check a calculation that comes from outside as you would any other.

Approvals travel as a record: the approver's name and date. A revision lapses an approval as it always does.
