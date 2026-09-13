# QR-Based Equipment Management System

**App name:** QR Equipment Manager

QR Equipment Manager is a local-first Streamlit application for managing
university lab, clinic/laboratory, company, factory, borrowed, and demo
equipment. Users scan the QR code attached to equipment to open the correct
Equipment Page, or enter an Equipment ID manually.

This Project 1 release is management-only. It supports equipment records,
official local documentation, setup and troubleshooting notes, service/contact
information, and service tracking. It is not a clinical decision support
system and does not provide diagnosis or treatment recommendations.

## Core Features

- Register equipment with a permanent `equipment_id`.
- Upload official equipment manuals locally.
- Generate one permanent QR code per equipment ID.
- Store only `equipment_id` in each QR code, never a URL.
- Scan QR codes through the browser camera after clicking **Scan QR**.
- Use manual Equipment ID entry as a fallback.
- Search the compact Equipment Library by ID, name, location, or supplier/vendor.
- View equipment details, documentation, notes, service dates, and contact info.
- Perform Manual Keyword Search against locally extracted PDF text.
- Update equipment data or manuals without regenerating the QR code.
- Manage up to six custom fields per equipment item.
- Delete equipment for authorized admin/debug cleanup with confirmation.

## Equipment Fields

Each equipment record supports:

- Equipment ID
- Equipment Name
- Location
- Description
- Supplier / Vendor
- Contact Person
- Contact Info
- Purchase Date
- Installation Date
- Last Service Date
- Next Service Date
- Setup Notes
- Troubleshooting Notes
- Up to six custom fields with a Field Name and Field Value

Example custom fields include Asset Tag, Warranty End Date, Calibration Due
Date, Service Interval, Department, and Responsible Person.

## QR Code Rules

QR content is only the equipment ID, for example:

```text
LAB-MICROSCOPE-001
```

QR codes do not contain full URLs. The QR code is generated when a new
Equipment ID is created and remains associated with that ID. Updating the name,
manual, service information, notes, or custom fields does not regenerate it.
Changing an Equipment ID is blocked because the physical QR sticker would need
to be replaced. Regeneration is available only through the explicit
**Regenerate QR** admin action.

## Pages

### Home

- Start the camera scanner intentionally with **Scan QR**.
- Stop or cancel scanning.
- Enter an Equipment ID manually.

### Equipment Library

- Search by Equipment ID, Equipment Name, Location, or Supplier/Vendor.
- View a compact bordered table sorted by Equipment ID.
- Open an Equipment Page through the row's **Show** link.
- View QR status only. QR downloads are managed elsewhere.

### Admin Panel

- Create new equipment and upload official PDF documentation.
- Update equipment fields and replace documentation.
- View existing QR images.
- Regenerate a QR only through explicit admin action.
- Delete equipment and optional local files after typing the Equipment ID to
  confirm.

### Equipment Page

- View equipment, supplier/contact, service, setup, and troubleshooting data.
- Open or download the local documentation PDF.
- Run Manual Keyword Search on extracted PDF text.
- View custom fields.

## Project 2 Direction

The earlier AI/manual-assistant ideas are intentionally preserved for a future
Project 2. Project 1 does not include AI features or an Ask AI interface.
Project 2 may later add documentation-grounded local AI search and question
answering as a separate stage, without changing the permanent QR design.

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Camera permission is requested only after the user clicks **Scan QR**.

## Local Storage and Public Repository Safety

Runtime data stays local in these folders:

- `manuals/`: uploaded PDF manuals.
- `data/`: SQLite database and extracted text.
- `qr_codes/`: generated QR images.

These directories contain `.gitkeep` files so the structure is available in a
fresh clone. Their runtime contents are ignored by Git. Do not commit uploaded
manuals, SQLite databases, generated QR images, or private/company/personal
equipment data.

## Technology Stack

- Python
- Streamlit
- SQLite
- `qrcode` and Pillow
- `pypdf` for PDF text extraction
- Browser-based QR scanning when available
