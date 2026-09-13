from __future__ import annotations

import html
import sqlite3
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

from backup_utils import BackupError, create_backup, read_backup, restore_backup
from database import (
    DB_PATH,
    add_field,
    create_record,
    delete_records,
    get_fields,
    get_record,
    get_records,
    initialize_db,
    remove_field,
    save_field_name,
    save_record_qr,
    save_record_value,
)
from field_utils import DATE_FORMATS, FIELD_TYPES, FIELD_TYPE_LABELS, display_value, widget_value
from label_utils import LABEL_SIZES, label_pdf, label_print_html
from qr_utils import generate_qr_code

APP_DIR = Path(__file__).resolve().parent
QRCODES_DIR = APP_DIR / "qr_codes"
st.set_page_config(page_title="QR Item Manager", page_icon=":material/qr_code_2:", layout="wide")
initialize_db(DB_PATH)


def go_to(page: str) -> None:
    st.query_params.clear()
    st.session_state["current_page"] = page
    st.session_state["scanner_active"] = False
    st.session_state["scroll_to_top"] = True
    st.session_state.pop("pending_delete", None)
    st.session_state.pop("pending_navigation", None)
    st.session_state.pop("pending_remove_field", None)
    st.session_state.pop("saved_feedback", None)
    st.session_state.pop("pending_print", None)
    st.session_state.pop("pending_restore", None)


def detail_input_key(record_id: str, field: dict) -> str:
    key = f"value_{record_id}_{field['id']}"
    return key if field["field_type"] == "Text" else f"{key}_{field['field_type']}_{field['date_format']}"


def last_updated(record: dict) -> str:
    if not record.get("updated_at"):
        return "Last updated: Not recorded"
    timestamp = datetime.fromisoformat(record["updated_at"])
    return f"Last updated: {timestamp:%Y-%m-%d %H:%M:%S} UTC"


def current_drafts() -> dict:
    """Map the current page's input keys to their persisted values."""
    page = st.session_state.get("current_page")
    if page == "Admin Panel":
        drafts = {}
        for field in get_fields(DB_PATH):
            for setting in ("field_name", "field_type", "date_format"):
                drafts[f"{setting}_{field['id']}"] = field[setting] or ""
        return drafts
    if page == "Detail Page":
        record_id = st.session_state.get("selected_record_id")
        record = get_record(DB_PATH, record_id) if record_id else None
        if record:
            drafts = {}
            for field in get_fields(DB_PATH, saved_only=True):
                key = detail_input_key(record_id, field)
                drafts[key] = widget_value(field, record["values"].get(field["id"], ""))
                drafts[f"{key}_clear"] = False
            return drafts
    return {}


def cancel_navigation() -> None:
    st.session_state.pop("pending_navigation", None)


def request_navigation(page: str) -> None:
    if page == st.session_state.get("current_page"):
        return
    drafts = current_drafts()
    if any(st.session_state.get(key, saved) != saved for key, saved in drafts.items()):
        st.session_state["pending_navigation"] = page
        st.session_state.pop("pending_remove_field", None)
        st.session_state.pop("pending_delete", None)
    else:
        go_to(page)


@st.dialog("Unsaved changes", width="small", on_dismiss=cancel_navigation)
def confirm_navigation(page: str) -> None:
    st.write("You have unsaved changes. Leave this page and discard them?")
    stay, leave = st.columns(2)
    if stay.button("Stay", key="stay_on_page", type="primary"):
        cancel_navigation()
        st.rerun()
    if leave.button("Leave", key="leave_page"):
        # Clear widget drafts at the start of the next full run, before rendering inputs.
        st.session_state["discard_input_keys"] = list(current_drafts())
        go_to(page)
        st.rerun()


def open_record(record_id: str, *, view_only: bool = False) -> bool:
    record_id = record_id.strip()
    if not get_record(DB_PATH, record_id):
        st.warning(f"Record ID '{record_id}' was not found.")
        return False
    page = "Library Record" if view_only else "Detail Page"
    if (st.session_state.get("selected_record_id"), st.session_state.get("current_page")) != (record_id, page):
        st.session_state["scroll_to_top"] = True
    st.session_state["selected_record_id"] = record_id
    st.session_state["current_page"] = page
    st.session_state["scanner_active"] = False
    return True


def set_scanner_active(active: bool) -> None:
    st.session_state["scanner_active"] = active


def render_home() -> None:
    st.html("""
        <style>
            .st-key-home_intro h1 {
                font-size: clamp(1.5rem, 2.8vw, 2.1rem);
                line-height: 1.3;
                text-align: center;
                padding-bottom: 0;
            }
            .st-key-home_scan_stage { margin-top: 1.5rem; }
            @keyframes home-scan-pulse {
                0%, 100% { transform: scale(0.833333); }
                50% { transform: scale(1); }
            }
            .st-key-home_scan_action button {
                box-sizing: border-box;
                width: 120px;
                min-width: 120px;
                height: 120px;
                min-height: 120px;
                padding: 0;
                aspect-ratio: 1;
                border: 5px solid #8cff32;
                border-radius: 50%;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                gap: 8px;
                text-align: center;
                transform-origin: center;
                animation: home-scan-pulse 2.4s ease-in-out infinite;
                box-shadow: 0 8px 24px rgba(255, 75, 75, 0.16);
            }
            .st-key-home_scan_action button:hover,
            .st-key-home_scan_action button:focus-visible {
                border-color: #8cff32;
                animation-play-state: paused;
            }
            @media (prefers-reduced-motion: reduce) {
                .st-key-home_scan_action button { animation: none; }
            }
            .st-key-home_scan_action button p {
                font-size: 1.25rem;
                font-weight: 600;
                line-height: 1.2;
                margin: 0;
                text-align: center;
            }
            .st-key-home_scan_action [data-testid="stMarkdownContainer"] {
                flex-grow: 0;
                margin: 0;
                padding: 0;
                text-align: center;
            }
            .st-key-home_scan_action button:focus-visible {
                outline: 3px solid #31333f;
                outline-offset: 5px;
            }
            .st-key-home_scan_hint p { text-align: center; }
        </style>
    """)
    with st.container(horizontal_alignment="center", gap="medium"):
        with st.container(key="home_intro", width=880):
            st.title("QR Item Manager")
        with st.container(key="home_scan_stage", width=420, horizontal_alignment="center", gap="small"):
            if not st.session_state.get("scanner_active"):
                with st.container(key="home_scan_action", width=120):
                    st.button("Scan QR", key="home_scan_start", type="primary",
                              on_click=set_scanner_active, args=(True,), width="stretch")
                with st.container(key="home_scan_hint", gap=None):
                    st.write("Scan an item QR code to view its details.")
                    st.caption("You can also browse records in Library.")
                st.button("How to use", key="home_help", type="tertiary",
                          on_click=go_to, args=("How to use",))
                return
            try:
                from scanner import qrcode_scanner
                st.caption("Camera preview · Place your QR code inside the square.")
                value = qrcode_scanner(key="record_qr_scanner")
            except ImportError:
                st.info("Browser QR scanning is unavailable. Use Library to search and view records.")
            else:
                if value:
                    if hasattr(value, "read"):
                        value = value.read()
                    if isinstance(value, bytes):
                        value = value.decode("utf-8")
                    if open_scanned_record(str(value)):
                        st.rerun()
            st.button("Stop Scanner", key="home_scan_stop", on_click=set_scanner_active, args=(False,))


def render_user_guide() -> None:
    with st.container(width=900):
        st.title("How to use")
        st.button("Back to Home", key="guide_back_home", on_click=go_to, args=("Home",))
        guide = (APP_DIR / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
        # The page title replaces the document's first heading.
        st.markdown(guide.split("\n", 1)[1])


def field_action(action, *args) -> bool:
    try:
        action(DB_PATH, *args)
    except ValueError as exc:
        st.session_state["field_error"] = str(exc)
        return False
    else:
        st.session_state.pop("field_error", None)
        return True


def save_admin_field(field_id: int) -> None:
    key = f"field_name_{field_id}"
    if field_action(save_field_name, field_id, st.session_state[key],
                    st.session_state[f"field_type_{field_id}"], st.session_state[f"date_format_{field_id}"]):
        st.session_state[key] = st.session_state[key].strip()
        st.session_state["saved_feedback"] = key


def cancel_field_removal() -> None:
    st.session_state.pop("pending_remove_field", None)


def request_field_removal(field_id: int) -> None:
    st.session_state["pending_remove_field"] = field_id


@st.dialog("Remove field?", width="small", on_dismiss=cancel_field_removal)
def confirm_field_removal(field_id: int) -> None:
    field = next((field for field in get_fields(DB_PATH) if field["id"] == field_id), None)
    if field is None:
        cancel_field_removal()
        st.rerun()
    st.write(field["field_name"] or "Unnamed field")
    st.warning("Removing this field also deletes its saved values from every record. This cannot be undone.")
    st.caption("QR status resets for any record left without saved field values.")
    yes, no = st.columns(2)
    if yes.button("YES", key="confirm_remove_field"):
        if field_action(remove_field, field_id):
            cancel_field_removal()
        st.rerun()
    if no.button("NO", key="cancel_remove_field"):
        cancel_field_removal()
        st.rerun()


def render_admin() -> None:
    st.title("Admin Panel")
    settings, backups = st.tabs(["Field Settings", "Backup & Restore"])
    with settings:
        render_field_settings()
    with backups:
        render_backups()


def render_field_settings() -> None:
    st.subheader("Field Settings")
    st.caption("Choose Text / Number for letters, numbers, or mixed values; choose Date for a calendar. Save applies the settings for that field.")
    if error := st.session_state.get("field_error"):
        st.error(error)
    fields = get_fields(DB_PATH)
    saved_feedback = st.session_state.pop("saved_feedback", None)
    for index, field in enumerate(fields):
        field_id = field["id"]
        input_key = f"field_name_{field_id}"
        type_key, format_key = f"field_type_{field_id}", f"date_format_{field_id}"
        for setting in ("field_name", "field_type", "date_format"):
            st.session_state.setdefault(f"{setting}_{field_id}", field[setting] or "")
        if st.session_state[type_key] == "Number":
            st.session_state[type_key] = "Text"
        with st.container(width=1100):
            label, entry, kind, date_format, remove, save, status = st.columns([1.1, 1.4, 1.45, 1.5, 0.8, 0.65, 0.8], gap="small", vertical_alignment="center")
            label.write(f"Field Name {index + 1}:")
            value = entry.text_input(
                f"Field Name {index + 1}",
                max_chars=10, key=input_key, label_visibility="collapsed",
            )
            selected_type = kind.selectbox(f"Type for Field Name {index + 1}", FIELD_TYPES,
                format_func=FIELD_TYPE_LABELS.get, key=type_key, label_visibility="collapsed")
            selected_format = date_format.selectbox(
                f"Date format for Field Name {index + 1}", DATE_FORMATS, key=format_key,
                label_visibility="collapsed", disabled=selected_type != "Date",
                help="DD/MM/YYYY: day first · MM/DD/YYYY: month first · YYYY/MM/DD: year first",
            )
            remove.button("Remove", key=f"remove_field_{field_id}", on_click=request_field_removal, args=(field_id,))
            changed = (value, selected_type, selected_format) != (field["field_name"] or "", field["field_type"], field["date_format"])
            save.button("Save", key=f"save_field_{field_id}", disabled=not changed, on_click=save_admin_field, args=(field_id,))
            if changed:
                status.caption("Unsaved")
            elif saved_feedback == input_key:
                status.caption("Saved ✓")
    if not fields:
        st.caption("No fields yet. Click Add to create a field.")
    st.button("Add", key="add_field", disabled=len(fields) >= 6, on_click=field_action, args=(add_field,))


def cancel_restore() -> None:
    st.session_state.pop("pending_restore", None)


def request_restore(payload: bytes) -> None:
    st.session_state["pending_restore"] = payload


def render_backups() -> None:
    st.subheader("Backup & Restore")
    st.caption("Keep a copy of your saved records, field settings, dates, last updated times, and QR codes.")
    if message := st.session_state.get("restore_success"):
        st.success(message)
    with st.container(border=True):
        st.write("**Backup**")
        st.write("Create a backup, then download the ZIP and keep it somewhere safe.")
        st.caption("Only saved changes are included. Create a new backup after making changes.")
        if st.button("Create backup", key="create_backup"):
            try:
                payload = create_backup(DB_PATH, QRCODES_DIR)
            except (BackupError, OSError, sqlite3.Error) as exc:
                st.error(f"Backup could not be created: {exc}")
            else:
                st.session_state["prepared_backup"] = payload
                st.session_state["prepared_backup_name"] = f"qr-item-manager-backup-{datetime.now():%Y%m%d-%H%M%S}.zip"
        if payload := st.session_state.get("prepared_backup"):
            summary = read_backup(payload)
            st.caption(f"Backup created: {summary['exported_at']} · {len(summary['records'])} records · {len(summary['fields'])} fields")
            if summary["missing_qr_images"]:
                st.warning("Some QR images are missing locally. Their records are included, but those QR codes will need to be generated again after restore.")
            st.download_button("Download backup ZIP", data=payload, file_name=st.session_state["prepared_backup_name"],
                               mime="application/zip", key="download_backup", on_click="ignore")
    with st.container(border=True):
        st.write("**Restore**")
        st.write("Upload a backup ZIP to review its contents before replacing the current records and field settings.")
        upload = st.file_uploader("Backup ZIP", type=["zip"], key="restore_upload")
        if upload is not None:
            payload = upload.getvalue()
            try:
                summary = read_backup(payload)
            except BackupError as exc:
                st.error(str(exc))
            else:
                st.caption(f"Created: {summary['exported_at']}")
                st.write(f"**{len(summary['records'])} records · {len(summary['fields'])} fields · {len(summary['images'])} active QR codes**")
                if summary["missing_qr_images"]:
                    st.warning("This backup has missing QR images. Those records will have QR status Not available.")
                st.button("Review restore", key="review_restore", on_click=request_restore, args=(payload,))
        st.caption("A backup of the current saved data is kept automatically before every restore.")
        safety_dir = APP_DIR / "data" / "backups"
        copies = sorted(safety_dir.glob("before-restore-*.zip"), reverse=True)
        if copies:
            selected = st.selectbox("Backup before restore", copies, format_func=lambda path: path.name, key="safety_backup_selection")
            st.download_button("Download previous data", data=selected.read_bytes(), file_name=selected.name,
                               mime="application/zip", key="download_safety_backup", on_click="ignore")


@st.dialog("Restore backup?", width="small", on_dismiss=cancel_restore)
def confirm_restore(payload: bytes) -> None:
    summary = read_backup(payload)
    st.write(f"Replace the current data with **{len(summary['records'])} records** and **{len(summary['fields'])} fields** from this backup?")
    st.warning("This replaces all current records and field settings, including unsaved edits. It does not merge records.")
    st.caption("Your current saved data will be backed up first. Record IDs and saved dates will be preserved.")
    cancel, restore = st.columns(2)
    if cancel.button("Cancel", key="cancel_restore"):
        cancel_restore()
        st.rerun()
    if restore.button("Restore and replace", key="confirm_restore", type="primary"):
        try:
            restore_backup(payload, DB_PATH, QRCODES_DIR, APP_DIR / "data" / "backups")
        except (BackupError, OSError, sqlite3.Error) as exc:
            st.error(f"Restore could not be completed. Current records were kept. {exc}")
        else:
            # Remove stale widgets before rendering the restored fields on the next run.
            st.session_state["discard_input_keys"] = [key for key in st.session_state if key.startswith(
                ("field_name_", "field_type_", "date_format_", "value_"))] + [
                "restore_upload", "prepared_backup", "prepared_backup_name", "selected_record_id",
                "field_error", "detail_error", "manage_search", "library_search", "safety_backup_selection",
            ]
            go_to("Admin Panel")
            st.session_state["restore_success"] = "Backup restored. Your previous data is available below under Download previous data."
            st.rerun()


def qr_available(record: dict) -> bool:
    return bool(
        any(value.strip() for value in record["values"].values())
        and record["qr_filename"]
        and (QRCODES_DIR / record["qr_filename"]).is_file()
    )


def open_scanned_record(record_id: str) -> bool:
    record = get_record(DB_PATH, record_id.strip())
    if record is None or not qr_available(record):
        st.warning("This QR is not active. Open the record from Manage, save a field value, and generate its QR again.")
        return False
    return open_record(record_id, view_only=True)


def clear_delete_confirmation() -> None:
    st.session_state.pop("pending_delete", None)


def add_empty_record() -> None:
    create_record(DB_PATH)
    # Show the newly added empty record even if the previous search excluded it.
    st.session_state["manage_search"] = ""
    clear_delete_confirmation()


@st.dialog("DELETE?", width="small", on_dismiss=clear_delete_confirmation)
def confirm_delete_dialog(record_ids: list[str]) -> None:
    st.caption(", ".join(record_ids))
    with st.container(width=180):
        yes, no = st.columns(2)
        if yes.button("YES", key="confirm_delete"):
            delete_records(DB_PATH, record_ids)
            clear_delete_confirmation()
            st.rerun()
        if no.button("NO", key="cancel_delete"):
            clear_delete_confirmation()
            st.rerun()


def request_record_delete(record_id: str) -> None:
    st.session_state["pending_delete"] = [record_id]


def render_records(*, view_only: bool = False) -> None:
    st.title("Library" if view_only else "Manage")
    st.html(
        """
        <style>
            .st-key-manage_toolbar { padding-top: 1px; }
            .st-key-manage_toolbar button {
                width: 40px;
                min-height: 28px;
                height: 28px;
                margin-top: 3px;
                padding: 2px 6px;
                border-radius: 6px;
            }
            .st-key-manage_toolbar button p {
                font-size: 14px;
                line-height: 1;
                white-space: nowrap;
            }
            [data-testid="stColumn"]:has(.st-key-manage_toolbar) {
                flex: 0 0 44px;
                min-width: 44px;
            }
            table.manage-records {
                width: 100%;
                table-layout: fixed;
                border-collapse: separate;
                border-spacing: 0;
                border: 1px solid #d9dfe8;
                border-radius: 8px;
                overflow: hidden;
                margin: 0;
                font-size: 16px;
            }
            table.manage-records th, table.manage-records td {
                box-sizing: border-box;
                height: 35px;
                padding: 0 8px;
                line-height: 34px;
                text-align: left;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                border: 0;
                border-right: 1px solid #d9dfe8;
                border-bottom: 1px solid #d9dfe8;
            }
            table.manage-records th {
                background: var(--secondary-background-color, #f7f8fa);
                font-weight: 400;
            }
            table.manage-records th:last-child, table.manage-records td:last-child {
                border-right: 0;
            }
            table.manage-records tbody tr:last-child td { border-bottom: 0; }
            table.manage-records a { color: #0068c9; text-decoration: none; }
            table.manage-records a:hover { text-decoration: underline; }
        </style>
        """,
    )
    query = st.text_input(
        "Search records", key="library_search" if view_only else "manage_search",
        on_change=None if view_only else clear_delete_confirmation,
    ).strip().casefold()
    fields = get_fields(DB_PATH, saved_only=True)
    records = [record for record in get_records(DB_PATH) if not query or any(
        query in value.casefold() for value in [record["record_id"], *record["values"].values(),
            *[display_value(field, record["values"].get(field["id"], "")) for field in fields]]
    )]
    if view_only:
        table = st.container()
    else:
        toolbar, table = st.columns([0.65, 9.35], gap="small")
        with toolbar, st.container(key="manage_toolbar", gap=None):
            # Match each button slot to the 35px header/record row beside it.
            with st.container(height=35, border=False, key="manage_add_slot"):
                st.button("Add", key="add_record", on_click=add_empty_record, width="content")
            for record in records:
                with st.container(height=35, border=False, key=f"delete_slot_{record['record_id']}"):
                    st.button(
                        "Del", key=f"delete_{record['record_id']}", width="content",
                        on_click=request_record_delete, args=(record["record_id"],),
                    )
    with table:
        columns = ["Record ID", *[field["field_name"] for field in fields], "QR Code"]
        header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
        rows = []
        for record in records:
            record_id = record["record_id"]
            parameter = "view_record" if view_only else "record_id"
            href = f"?{parameter}={quote(record_id, safe='')}"
            id_cell = f'<td><a href="{href}" target="_self">{html.escape(record_id)}</a></td>'
            values = [display_value(field, record["values"].get(field["id"], "")) for field in fields]
            values.append("Available" if qr_available(record) else "Not available")
            cells = "".join(
                f'<td title="{html.escape(value, quote=True)}">{html.escape(value)}</td>' for value in values
            )
            rows.append(f"<tr>{id_cell}{cells}</tr>")
        st.markdown(
            f'<table class="manage-records"><thead><tr>{header}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>',
            unsafe_allow_html=True,
        )
        if not records:
            st.caption("No records match your search." if query else (
                "No records yet." if view_only else "Click Add to create your first record."
            ))


def edit_library_record(record_id: str) -> None:
    if open_record(record_id):
        # Replace the view route so reruns keep the editable page open.
        st.query_params.clear()
        st.query_params["record_id"] = record_id


def render_library_record(record_id: str) -> None:
    st.title("Library")
    record = get_record(DB_PATH, record_id)
    if record is None:
        st.warning("This record no longer exists.")
    else:
        details, qr = st.columns([3, 1], gap="large")
        with details:
            st.write(f"**Record ID: {record_id}**")
            st.caption(last_updated(record))
            fields = get_fields(DB_PATH, saved_only=True)
            rows = []
            for field in fields:
                value = display_value(field, record["values"].get(field["id"], ""))
                rows.append(
                    f'<tr><th scope="row">{html.escape(field["field_name"])}</th>'
                    f'<td>{html.escape(value)}</td></tr>'
                )
            if fields:
                st.markdown(
                    '<style>.library-details { width: 100%; border-collapse: collapse; }'
                    '.library-details th, .library-details td { padding: 12px 16px; '
                    'border: 1px solid #d9dfe8; text-align: left; vertical-align: top; '
                    'white-space: pre-wrap; overflow-wrap: anywhere; }'
                    '.library-details th { width: 32%; font-weight: 500; '
                    'background: var(--secondary-background-color, #f7f8fa); }</style>'
                    f'<table class="library-details"><tbody>{"".join(rows)}</tbody></table>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("No field information is available for this record.")
        with qr:
            st.write("**QR Code**")
            if qr_available(record):
                st.image(str(QRCODES_DIR / record["qr_filename"]), width=180, caption=record_id)
            else:
                st.caption("Not available")
    with st.container(width=400):
        back, edit = st.columns([1.8, 1], gap="small")
        back.button("Back to Library", key="library_back", on_click=request_navigation, args=("Library",))
        if record is not None:
            edit.button("Edit Record", key="library_manage", on_click=edit_library_record, args=(record_id,))


def scroll_to_top() -> None:
    """Reset the retained Streamlit scroll position after opening a new page."""
    if st.session_state.pop("scroll_to_top", False):
        components.html(
            """<script>
            function resetScroll() {
                const doc = window.parent.document;
                const main = doc.querySelector('[data-testid="stMain"]') || doc.querySelector('.main');
                if (main) main.scrollTo({top: 0, left: 0, behavior: 'instant'});
                window.parent.scrollTo({top: 0, left: 0, behavior: 'instant'});
            }
            requestAnimationFrame(resetScroll);
            setTimeout(resetScroll, 100);
            </script>""", height=0,
        )


def save_detail_field(record_id: str, field_id: int) -> None:
    field = next((field for field in get_fields(DB_PATH, saved_only=True) if field["id"] == field_id), None)
    if field is None:
        st.session_state["detail_error"] = "This field no longer exists."
        return
    key = detail_input_key(record_id, field)
    try:
        save_record_value(DB_PATH, record_id, field_id, st.session_state[key])
    except ValueError as exc:
        st.session_state["detail_error"] = str(exc)
    else:
        st.session_state.pop("detail_error", None)
        st.session_state["saved_feedback"] = key
        st.session_state.pop(f"{key}_clear", None)


def cancel_label_print() -> None:
    st.session_state.pop("pending_print", None)


def request_label_print(record_id: str) -> None:
    st.session_state["pending_print"] = record_id


@st.dialog("Print QR label", width="small", on_dismiss=cancel_label_print)
def print_label_dialog(record_id: str) -> None:
    record = get_record(DB_PATH, record_id)
    if record is None or not qr_available(record):
        st.info("This QR is no longer available. Generate it from the record first.")
        return
    size = st.selectbox("Label size", LABEL_SIZES, index=1,
                        format_func=lambda size: f"{size} × {size} mm", key="label_size")
    st.caption("Print at 100% / Actual size with browser headers and footers off. Match your printer paper size to the label.")
    png = (QRCODES_DIR / record["qr_filename"]).read_bytes()
    components.html(label_print_html(record_id, png, size), height=int(size * 96 / 25.4) + 65)
    st.download_button("Download label PDF", data=label_pdf(record_id, size),
        file_name=f"{record_id}-label-{size}mm.pdf", mime="application/pdf", key="download_label", on_click="ignore")


def render_detail(record_id: str) -> None:
    st.html(
        """<style>
        .st-key-detail_heading h1 {
            font-size: 2rem;
            line-height: 1.3;
            margin: 0;
            padding: 0 0 0.5rem;
        }
        .st-key-detail_fields { gap: 0.5rem !important; }
        .st-key-detail_fields button {
            min-height: 36px;
            padding: 4px 10px;
        }
        .st-key-detail_fields button p { font-size: 13px; white-space: nowrap; }
        .st-key-detail_fields .detail-field-label { font-size: 13px; line-height: 1.4; }
        </style>""",
    )
    with st.container(key="detail_heading", gap="small"):
        st.title("Record Details")
        st.caption(f"Record ID: {record_id}")
    record = get_record(DB_PATH, record_id)
    if not record:
        st.warning("This record no longer exists.")
        st.button("DONE", on_click=request_navigation, args=("Manage",))
        return
    fields = get_fields(DB_PATH, saved_only=True)
    unsaved = False
    saved_feedback = st.session_state.pop("saved_feedback", None)
    with st.container(width=1000):
        record_info, actions = st.columns([2.3, 1], gap="large", vertical_alignment="center")
        record_info.caption(last_updated(record))
        actions.button("DONE", key="detail_done", on_click=request_navigation, args=("Manage",))
        # Column borders stretch together to the taller card's content height.
        details, qr = st.columns([2.3, 1], gap="large", border=True)
        with details:
            with st.container(key="detail_fields", border=False, gap="small"):
                if error := st.session_state.get("detail_error"):
                    st.error(error)
                for field in fields:
                    field_id = field["id"]
                    saved_value = record["values"].get(field_id, "")
                    input_key = detail_input_key(record_id, field)
                    original = widget_value(field, saved_value)
                    if input_key not in st.session_state:
                        st.session_state[input_key] = original
                    with st.container(key=f"detail_row_{field_id}", gap="small"):
                        st.markdown(f'<div class="detail-field-label">{html.escape(field["field_name"])}</div>', unsafe_allow_html=True)
                        entry, save, status = st.columns([4.8, 1, 1.2], gap="small", vertical_alignment="center")
                        if field["field_type"] == "Date":
                            value = entry.date_input(field["field_name"], value=None, key=input_key,
                                format=field["date_format"], min_value=date(1, 1, 1), max_value=date(9999, 12, 31), label_visibility="collapsed")
                        else:
                            value = entry.text_input(field["field_name"], key=input_key, label_visibility="collapsed")
                        clear = False
                        if original is None and saved_value.strip():
                            st.caption(f"Previous saved text: {saved_value}. Choose a {field['field_type'].lower()} and Save to replace it.")
                            if value is None:
                                clear = st.checkbox("Clear saved value", key=f"{input_key}_clear")
                        changed = value != original or clear
                        save.button("Save", key=f"save_value_{field_id}", disabled=not changed, on_click=save_detail_field, args=(record_id, field_id))
                        if changed:
                            status.caption("Unsaved")
                            unsaved = True
                        elif saved_feedback == input_key:
                            status.caption("Saved ✓")
                if not fields:
                    st.info("Set and save field names in Admin Panel first.")
        with qr, st.container(key="detail_qr", border=False):
            st.write("**QR Code**")
            available = qr_available(record)
            has_saved_values = any(record["values"].get(field["id"], "").strip() for field in fields)
            if available:
                qr_path = QRCODES_DIR / record["qr_filename"]
                st.image(str(qr_path), width=180, caption=record_id)
                st.caption("QR status: Available")
                st.download_button(
                    "Download QR", data=qr_path.read_bytes(), file_name=f"{record_id}.png",
                    mime="image/png", key="download_qr", on_click="ignore",
                )
                st.button("Print QR label", key="print_qr_label", on_click=request_label_print, args=(record_id,))
            else:
                st.caption("QR status: Not available")
                if st.button("Generate QR", disabled=unsaved or not has_saved_values, key="generate_qr") and not unsaved and has_saved_values:
                    try:
                        filename = generate_qr_code(record_id, QRCODES_DIR)
                        save_record_qr(DB_PATH, record_id, filename)
                    except ValueError as exc:
                        st.error(str(exc))
                    except OSError:
                        st.error("The QR image could not be saved. Please try again.")
                    else:
                        st.rerun()
            if unsaved:
                st.caption("Save each edited field before generating QR or leaving this page.")
            elif not has_saved_values and not available:
                st.caption("Save at least one field value to enable Generate QR.")


def main() -> None:
    st.html(
        """
        <style>
            [data-testid="stMainBlockContainer"] {
                padding-top: 3.75rem;
            }
            @media (min-width: 769px) {
                [data-testid="stSidebar"][aria-expanded="true"] {
                    width: 200px !important;
                    min-width: 200px !important;
                    max-width: 200px !important;
                }
            }
            [data-testid="stSidebarUserContent"] { padding-left: 16px; padding-right: 16px; }
            .st-key-sidebar_menu { border-top: 1px solid #d9dfe8; }
            .st-key-sidebar_menu button {
                width: 100%;
                min-height: 44px;
                padding: 8px 12px;
                border: 0;
                border-bottom: 1px solid #d9dfe8;
                border-left: 3px solid transparent;
                border-radius: 0;
                background: transparent;
                color: inherit;
                box-shadow: none;
                justify-content: flex-start;
            }
            .st-key-sidebar_menu button p { font-size: 16px; }
            .st-key-sidebar_menu button:hover { background: rgba(128, 128, 128, 0.08); }
            .st-key-sidebar_menu button[data-testid="stBaseButton-primary"] {
                background: rgba(255, 75, 75, 0.09);
                border-left-color: #ff4b4b;
                color: #c93636;
            }
            .st-key-sidebar_menu button[data-testid="stBaseButton-primary"] p { font-weight: 600; }
        </style>
        """,
    )
    for key in st.session_state.pop("discard_input_keys", []):
        st.session_state.pop(key, None)
    st.session_state.setdefault("current_page", "Home")
    # Keep an already-running session usable after the page rename.
    old_pages = {"Admin Upload": "Admin Panel"}
    page = st.session_state["current_page"]
    st.session_state["current_page"] = old_pages.get(page, page)
    if record_id := st.query_params.get("view_record"):
        open_record(record_id, view_only=True)
    elif record_id := st.query_params.get("record_id"):
        open_record(record_id)
    with st.sidebar:
        st.title("Menu")
        current_page = st.session_state["current_page"]
        active_menu = {"Detail Page": "Manage", "Library Record": "Library", "How to use": "Home"}.get(current_page, current_page)
        with st.container(key="sidebar_menu", gap=None):
            for page in ["Home", "Library", "Manage", "Admin Panel"]:
                st.button(
                    page, key=f"nav_{page}", type="primary" if page == active_menu else "secondary",
                    width="stretch", on_click=request_navigation, args=(page,),
                )
    page = st.session_state["current_page"]
    if page == "Manage":
        render_records()
    elif page == "Library":
        render_records(view_only=True)
    elif page == "Library Record" and st.session_state.get("selected_record_id"):
        render_library_record(st.session_state["selected_record_id"])
    elif page == "Admin Panel":
        render_admin()
    elif page == "How to use":
        render_user_guide()
    elif page == "Detail Page" and st.session_state.get("selected_record_id"):
        render_detail(st.session_state["selected_record_id"])
    else:
        render_home()
    scroll_to_top()
    if pending_page := st.session_state.get("pending_navigation"):
        confirm_navigation(pending_page)
    elif field_id := st.session_state.get("pending_remove_field"):
        confirm_field_removal(field_id)
    elif pending := st.session_state.get("pending_delete"):
        confirm_delete_dialog(pending)
    elif record_id := st.session_state.get("pending_print"):
        print_label_dialog(record_id)
    elif payload := st.session_state.get("pending_restore"):
        confirm_restore(payload)


if __name__ == "__main__":
    main()
