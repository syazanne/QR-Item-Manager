# Retained reference and compatibility code

The application entry point is `app.py`. The items below are kept intentionally;
they are not additional pages or features users need to configure.

| Item | Why it is retained |
| --- | --- |
| `pdf_utils.py` | Standalone PDF text extraction and manual-search helpers from the earlier prototype. The current app does not import it. |
| `manuals/` and `data/manual_text/` | Earlier local manual assets. Their contents are ignored by Git and unused by the current interface. |
| `_reset_backup/` | Earlier local recovery copies. The folder is ignored by Git. Do not remove it as part of code cleanup. |
| Database migration code | Imports older equipment records and upgrades field settings while preserving saved data and IDs. |
| Legacy database tables | Earlier import sources remain in the local database. Active record backups do not export them. |
| Old QR image files | Clearing a QR reference or deleting a record does not delete every old image. The database reference determines which QR is active. |
| `QR-MedTech` backup identifier | Accepted so backups made before the app rename still restore. New backups use `QR Item Manager`. |
| `Number` field migration | Converts older numeric fields into Text / Number without rewriting their values. |
| `Admin Upload` page alias | Lets a session left on the older page name reach Admin Panel after a code update. |

`QR1.py` was removed because it contained only an experiment-placeholder docstring.
It had no application logic or callers.

All dependencies in `requirements.txt` support the current app. In particular,
`pypdf` is required for printable QR-label PDFs, even though the separate
`pdf_utils.py` helper is reference-only. PyMuPDF is an optional fallback in that
helper, not an app dependency.
