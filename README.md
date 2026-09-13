# QR-Based Equipment Support and Management System

A local-first Streamlit application for managing equipment documentation and
quick support access through QR codes.

This is an equipment support and management system, not a clinical decision
support system. Users scan a QR code attached to equipment to open the correct
equipment page. The QR code stores only the stable `equipment_id` value, never a
URL, so the QR label remains independent of the local app address.

## What This System Does

- Registers equipment with an ID, name, location, and description.
- Uploads official or verified PDF documentation locally.
- Generates one QR code per equipment ID.
- Opens an equipment page from a browser camera scan or manual ID entry.
- Provides local keyword search across extracted PDF text.
- Supports manual, setup notes, troubleshooting notes, service information,
  and supplier/contact information as the equipment workflow grows.
- Preserves the existing QR code when equipment details or documentation are
  updated.
- Includes a placeholder for future local AI manual search.

## Use Cases

- University lab equipment management.
- Clinic or laboratory equipment quick reference.
- Borrowed or demo equipment support.
- Factory equipment support.
- Service and maintenance information tracking.

## What This System Does Not Do

- It does not make clinical decisions.
- It does not provide diagnosis or treatment recommendations.
- It does not replace official training or safety procedures.
- It does not search the internet for manuals.
- It only uses documentation uploaded and verified by an authorized user.
- It does not currently provide external AI answers; the AI area is a
  placeholder for a future documentation-grounded feature.

## Version 1 Features

### Home

- Start browser-based QR scanning only after the user clicks **Scan QR**.
- Use manual equipment ID entry as a backup.
- Open the matching equipment page from the local SQLite database.

### Equipment Library

- Search by equipment ID, name, or location.
- View a compact table of registered equipment.
- Open an equipment page from the table.
- See whether verified documentation and a QR code are available.

### Admin Equipment Upload

- Create new equipment records and upload official PDF documentation.
- Extract searchable text locally using `pypdf`.
- Generate a QR code containing only the equipment ID.
- Update details or replace documentation without changing the QR code.
- Explicitly regenerate a QR code only when needed.
- Delete records and local files only after typing the equipment ID to confirm.

### Equipment Page

- Display equipment details, location, description, and documentation status.
- Download or open the uploaded PDF locally.
- Search extracted documentation by keyword.
- Show a future AI manual search placeholder.

## QR Code Design

QR codes contain only the stable equipment ID, for example:

```text
LAB-MICROSCOPE-001
```

They never contain a full URL. Updating the equipment name, location,
description, service information, or PDF documentation does not create a new
QR code. A new QR code is generated only when a new equipment ID is created or
an authorized user explicitly selects **Regenerate QR**.

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit in a browser. Camera permission is
requested only after the user starts the QR scanner.

## Local Storage and Public Repo Safety

Runtime files stay local:

- `manuals/`: uploaded PDF documentation.
- `data/`: SQLite database and extracted text.
- `qr_codes/`: generated QR images.

These folders are kept in the project with `.gitkeep` files, while their
contents are ignored by Git. Database files, uploaded documents, generated QR
images, Python environments, caches, and local spreadsheets are not intended
for the public repository. Do not upload private, company, personal, or
confidential equipment data.

## Technology Stack

- Python
- Streamlit
- SQLite
- `qrcode` and Pillow
- `pypdf` for PDF text extraction
- Browser-based QR scanning when available

## Future Improvements

- Structured service and maintenance history.
- Supplier and contact fields.
- Role-based administration.
- Offline/local AI search grounded only in verified documentation.
- Export and reporting tools.
