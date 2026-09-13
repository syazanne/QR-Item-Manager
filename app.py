from __future__ import annotations

import html
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import streamlit as st

from database import (
    DB_PATH,
    delete_machine,
    get_all_machines,
    get_machine_by_id,
    initialize_db,
    insert_machine,
    update_machine,
    update_qr_filename,
)
from pdf_utils import extract_pdf_text, search_manual_text
from qr_utils import generate_qr_code

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
MANUALS_DIR = APP_DIR / "manuals"
QRCODES_DIR = APP_DIR / "qr_codes"

for directory in (DATA_DIR, MANUALS_DIR, QRCODES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

initialize_db(DB_PATH)

st.set_page_config(page_title="QR-Based Equipment Support and Management System", page_icon="🔧", layout="wide")


def navigate_to_machine(machine_id: str) -> None:
    machine_id = (machine_id or "").strip()
    if not machine_id:
        st.warning("Please enter a valid machine ID.")
        return

    machine = get_machine_by_id(DB_PATH, machine_id)
    if machine is None:
        st.warning(f"Equipment ID '{machine_id}' was not found in the local database.")
        return

    st.session_state["selected_machine_id"] = machine_id
    st.session_state["current_page"] = "Equipment Page"


def handle_machine_query_parameter() -> None:
    """Open an equipment page when a Library link includes its equipment ID."""
    machine_id = st.query_params.get("machine_id")
    if machine_id:
        navigate_to_machine(machine_id)


def render_qr_scanner() -> Optional[str]:
    """Use the optional browser scanner, while keeping manual entry available."""
    try:
        from streamlit_qrcode_scanner import qrcode_scanner
    except ImportError:
        st.info("Browser QR scanning is unavailable. Enter the equipment ID below.")
        return None

    scanned_value = qrcode_scanner(key="machine_qr_scanner")
    if not scanned_value:
        return None
    if isinstance(scanned_value, bytes):
        return scanned_value.decode("utf-8").strip()
    if hasattr(scanned_value, "read"):
        return scanned_value.read().decode("utf-8").strip()
    return str(scanned_value).strip()


def render_home() -> None:
    st.title("QR-Based Equipment Support and Management System")
    st.markdown(
        """
        A local-first system for accessing verified equipment information, manuals, setup notes, troubleshooting notes, and service details by scanning a QR code or entering an equipment ID.
        """
    )

    st.subheader("Scan QR")
    st.caption("Click Scan QR when you are ready to use the browser camera.")

    if not st.session_state["scanner_active"]:
        if st.button("Scan QR", type="primary"):
            st.session_state["scanner_active"] = True
            st.rerun()
    else:
        if st.button("Stop Scanner"):
            st.session_state["scanner_active"] = False
            st.rerun()

        st.caption("Allow camera access when prompted, then point the camera at an equipment QR code.")
        scan_result = render_qr_scanner()
        if scan_result:
            st.session_state["scanner_active"] = False
            navigate_to_machine(scan_result)

    st.markdown("---")
    st.subheader("Manual Equipment ID Backup")
    manual_machine_id = st.text_input("Enter Equipment ID", key="manual_machine_id_home")
    if st.button("Open Equipment Page"):
        navigate_to_machine(manual_machine_id)


def render_library() -> None:
    st.title("Equipment Library")
    search_query = st.text_input(
        "Search equipment",
        placeholder="Search by equipment ID, name, or location",
        key="library_search",
    ).strip().lower()
    machines = sorted(get_all_machines(DB_PATH), key=lambda machine: machine["machine_id"].lower())

    if search_query:
        machines = [
            machine
            for machine in machines
            if any(
                search_query in str(machine[field] or "").lower()
                for field in ("machine_id", "machine_name", "location")
            )
        ]

    if not machines:
        if search_query:
            st.info("No equipment matches your search.")
        else:
            st.info("No equipment is registered yet. Use the Admin Upload page to add the first item.")
        return

    st.caption(f"Showing {len(machines)} equipment item(s), sorted by equipment ID.")
    table_rows = []
    for machine in machines:
        machine_id = html.escape(str(machine["machine_id"]))
        machine_name = html.escape(str(machine["machine_name"]))
        location = html.escape(str(machine["location"]))
        machine_url = f"?machine_id={quote(str(machine['machine_id']))}"
        qr_status = "Available" if machine["qr_filename"] else "Not available"
        table_rows.append(
            f'<tr><td>{machine_id}</td><td>{machine_name}</td>'
            f'<td>{location}</td><td><a href="{machine_url}" '
            f'target="_self" rel="noopener">Show</a></td><td>{qr_status}</td></tr>'
        )

    st.markdown(
        """
        <style>
            .machine-library-table {
                width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                border: 1px solid #d9dfe8;
                border-radius: 8px;
                overflow: hidden;
                font-size: 0.95rem;
            }
            .machine-library-table th,
            .machine-library-table td {
                padding: 0.55rem 0.75rem;
                border-right: 1px solid #d9dfe8;
                border-bottom: 1px solid #d9dfe8;
                text-align: left;
                line-height: 1.25;
            }
            .machine-library-table th {
                background: #f1f4f8;
                font-weight: 600;
            }
            .machine-library-table th:last-child,
            .machine-library-table td:last-child {
                border-right: 0;
            }
            .machine-library-table tr:last-child td {
                border-bottom: 0;
            }
            .machine-library-table a {
                font-weight: 600;
                text-decoration: none;
            }
            .machine-library-table a:hover {
                text-decoration: underline;
            }
        </style>
        <table class="machine-library-table">
            <thead>
                <tr>
                    <th>Equipment ID</th>
                    <th>Equipment Name</th>
                    <th>Location</th>
                    <th>Equipment Page</th>
                    <th>QR Code</th>
                </tr>
            </thead>
            <tbody>
        """
        + "".join(table_rows)
        + """
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


def render_admin_upload() -> None:
    st.title("Admin Equipment Upload")
    st.caption("Register equipment, upload verified documentation, and generate a QR code that stores only the equipment ID.")

    with st.form("machine_upload_form"):
        machine_id = st.text_input("Equipment ID")
        machine_name = st.text_input("Equipment Name")
        location = st.text_input("Location")
        description = st.text_area("Description")
        uploaded_pdf = st.file_uploader("Upload equipment documentation PDF", type=["pdf"])

        submitted = st.form_submit_button("Create New Equipment + Generate QR", type="primary")

        if submitted:
            if not machine_id or not machine_name or not location:
                st.error("Equipment ID, equipment name, and location are required.")
                return

            machine_id = machine_id.strip()
            existing_machine = get_machine_by_id(DB_PATH, machine_id)
            if existing_machine:
                st.warning(
                    f"Equipment ID '{machine_id}' already exists. Its details are shown below in "
                    "Manage Existing Equipment; the existing QR code was not changed."
                )
                st.session_state["admin_selected_machine"] = machine_id
                return

            if not uploaded_pdf:
                st.error("Please upload verified equipment documentation before continuing.")
                return

            safe_filename = f"{machine_id}_{Path(uploaded_pdf.name).name}"
            manual_path = MANUALS_DIR / safe_filename
            with open(manual_path, "wb") as file:
                file.write(uploaded_pdf.getvalue())

            try:
                manual_text = extract_pdf_text(manual_path)
            except Exception as exc:
                manual_path.unlink(missing_ok=True)
                st.error(f"The PDF could not be read: {exc}")
                return
            text_index_dir = DATA_DIR / "manual_text"
            text_index_dir.mkdir(parents=True, exist_ok=True)
            text_index_path = text_index_dir / f"{machine_id}.txt"
            text_index_path.write_text(manual_text, encoding="utf-8")

            qr_filename = generate_qr_code(machine_id, QRCODES_DIR)

            insert_machine(
                DB_PATH,
                {
                    "machine_id": machine_id,
                    "machine_name": machine_name,
                    "location": location,
                    "description": description,
                    "manual_filename": manual_path.name,
                    "qr_filename": qr_filename,
                },
            )

            st.success(f"Equipment '{machine_name}' was registered successfully.")
            st.image(str(QRCODES_DIR / qr_filename), caption=f"QR code for {machine_id}", width=260)

            st.caption(f"Documentation saved to: {manual_path.name}")
            st.caption(f"Searchable text saved to: {text_index_path.name}")

    st.markdown("---")
    st.subheader("Manage Existing Equipment")
    machines = get_all_machines(DB_PATH)
    if not machines:
        st.info("Register equipment above before editing it.")
        return

    admin_search = st.text_input(
        "Search existing equipment",
        placeholder="Search by equipment ID, name, or location",
        key="admin_machine_search",
    ).strip().lower()
    filtered_machines = [
        machine
        for machine in machines
        if not admin_search
        or any(
            admin_search in str(machine[field] or "").lower()
            for field in ("machine_id", "machine_name", "location")
        )
    ]
    if not filtered_machines:
        st.info("No existing equipment matches your search.")
        return

    machine_ids = [machine["machine_id"] for machine in filtered_machines]
    if st.session_state.get("admin_selected_machine") not in machine_ids:
        st.session_state["admin_selected_machine"] = machine_ids[0]
    selected_id = st.selectbox("Select equipment", machine_ids, key="admin_selected_machine")
    existing_machine = get_machine_by_id(DB_PATH, selected_id)

    if existing_machine is None:
        return

    existing_qr_path = QRCODES_DIR / (existing_machine["qr_filename"] or "")
    if existing_machine["qr_filename"] and existing_qr_path.exists():
        st.image(existing_qr_path, caption=f"Existing QR code for {selected_id}", width=220)

    with st.form("machine_update_form"):
        edited_machine_id = st.text_input(
            "Equipment ID (permanent)",
            value=existing_machine["machine_id"],
            help="Equipment IDs are permanent because they are stored in the physical QR sticker.",
        )
        edited_machine_name = st.text_input("Equipment Name", value=existing_machine["machine_name"])
        edited_location = st.text_input("Location", value=existing_machine["location"])
        edited_description = st.text_area("Description", value=existing_machine["description"] or "")
        replacement_pdf = st.file_uploader(
            "Replace manual PDF (optional)",
            type=["pdf"],
            key="replacement_manual_pdf",
        )
        update_submitted = st.form_submit_button("Save Machine Updates")

    if update_submitted:
        edited_machine_id = edited_machine_id.strip()
        if edited_machine_id != existing_machine["machine_id"]:
            st.warning(
                "Equipment ID cannot be changed here. Changing it would require a new QR code, "
                "and the physical QR sticker may need to be replaced."
            )
        elif not edited_machine_name or not edited_location:
            st.error("Equipment name and location are required.")
        else:
            manual_filename = existing_machine["manual_filename"]
            new_manual_path = None
            if replacement_pdf:
                safe_filename = f"{selected_id}_{Path(replacement_pdf.name).name}"
                new_manual_path = MANUALS_DIR / safe_filename
                new_manual_path.write_bytes(replacement_pdf.getvalue())
                try:
                    manual_text = extract_pdf_text(new_manual_path)
                except Exception as exc:
                    new_manual_path.unlink(missing_ok=True)
                    st.error(f"The replacement PDF could not be read: {exc}")
                    return

                text_index_dir = DATA_DIR / "manual_text"
                text_index_dir.mkdir(parents=True, exist_ok=True)
                (text_index_dir / f"{selected_id}.txt").write_text(manual_text, encoding="utf-8")
                manual_filename = new_manual_path.name

            update_machine(
                DB_PATH,
                selected_id,
                {
                    "machine_name": edited_machine_name,
                    "location": edited_location,
                    "description": edited_description,
                    "manual_filename": manual_filename,
                },
            )

            if new_manual_path and existing_machine["manual_filename"]:
                old_manual_path = MANUALS_DIR / existing_machine["manual_filename"]
                if old_manual_path != new_manual_path:
                    old_manual_path.unlink(missing_ok=True)

            st.success(
                "Equipment details were updated. The existing QR code was preserved."
            )

    st.caption(f"Current equipment QR code: {existing_machine['qr_filename'] or 'Not generated'}")
    if st.button("Regenerate QR", key="regenerate_qr"):
        qr_filename = generate_qr_code(selected_id, QRCODES_DIR)
        update_qr_filename(DB_PATH, selected_id, qr_filename)
        st.warning(
            "QR code regenerated for the same equipment ID. Replace the physical QR sticker if the old sticker is no longer being used."
        )
        st.image(str(QRCODES_DIR / qr_filename), caption=f"Regenerated QR code for {selected_id}", width=260)

    st.markdown("---")
    st.subheader("Delete Equipment")
    st.warning("This is a debugging/admin cleanup action. It cannot be undone.")
    remove_manual = st.checkbox(
        "Also delete the uploaded manual PDF",
        value=True,
        key="delete_manual_file",
    )
    remove_qr = st.checkbox(
        "Also delete the QR image",
        value=True,
        key="delete_qr_file",
    )
    delete_confirmation = st.text_input(
        "Type the equipment ID to confirm deletion",
        key="delete_machine_confirmation",
    ).strip()
    if st.button("Delete Equipment", type="secondary", key="delete_machine_button"):
        if delete_confirmation != selected_id:
            st.error("Deletion cancelled: the equipment ID does not match.")
        else:
            delete_machine(DB_PATH, selected_id)
            (DATA_DIR / "manual_text" / f"{selected_id}.txt").unlink(missing_ok=True)
            if remove_manual and existing_machine["manual_filename"]:
                (MANUALS_DIR / existing_machine["manual_filename"]).unlink(missing_ok=True)
            if remove_qr and existing_machine["qr_filename"]:
                (QRCODES_DIR / existing_machine["qr_filename"]).unlink(missing_ok=True)
            if st.session_state.get("selected_machine_id") == selected_id:
                st.session_state["selected_machine_id"] = None
                st.session_state["current_page"] = "Library"
            st.session_state["delete_machine_confirmation"] = ""
            st.success(f"Equipment '{selected_id}' was deleted.")


def render_machine_page(selected_machine_id: str) -> None:
    machine = get_machine_by_id(DB_PATH, selected_machine_id)

    if machine is None:
        st.warning("No equipment was selected. Please choose equipment from the Library or Home page.")
        return

    back_col1, back_col2 = st.columns([1, 1])
    with back_col1:
        if st.button("← Back to Equipment Library", key="back_to_library"):
            st.query_params.clear()
            st.session_state["current_page"] = "Library"
            st.session_state["selected_machine_id"] = None
            st.rerun()
    with back_col2:
        if st.button("← Back to Home", key="back_to_home"):
            st.query_params.clear()
            st.session_state["current_page"] = "Home"
            st.session_state["selected_machine_id"] = None
            st.rerun()

    st.title(f"Equipment: {machine['machine_name']}")
    st.caption(f"Equipment ID: {machine['machine_id']}")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Equipment Details")
        st.write(f"**Equipment ID:** {machine['machine_id']}")
        st.write(f"**Equipment Name:** {machine['machine_name']}")
        st.write(f"**Location:** {machine['location']}")
        st.write(f"**Description:** {machine['description'] or 'No description provided.'}")
        st.write(f"**Documentation File:** {machine['manual_filename'] or 'Not uploaded'}")

    with col2:
        qr_path = QRCODES_DIR / (machine['qr_filename'] if machine['qr_filename'] else "")
        if qr_path.exists():
            st.image(str(qr_path), width=220, caption="Equipment QR Code")

    st.markdown("---")

    manual_filename = machine["manual_filename"]
    if manual_filename:
        manual_path = MANUALS_DIR / manual_filename
        if manual_path.exists():
            st.subheader("Documentation Access")
            col_a, col_b = st.columns([1, 1])
            with col_a:
                with open(manual_path, "rb") as file:
                    st.download_button(
                        label="Download Documentation PDF",
                        data=file.read(),
                        file_name=manual_filename,
                        mime="application/pdf",
                    )
            with col_b:
                try:
                    st.markdown(f"[Open documentation PDF in browser]({manual_path.as_uri()})")
                except Exception:
                    st.caption("The manual file is available locally and can be downloaded above.")

    st.markdown("---")
    st.subheader("Documentation Search")
    search_query = st.text_input("Search by keyword", key=f"manual_search_{selected_machine_id}")
    if search_query:
        text_index_path = DATA_DIR / "manual_text" / f"{selected_machine_id}.txt"
        if text_index_path.exists():
            manual_text = text_index_path.read_text(encoding="utf-8")
            matches = search_manual_text(manual_text, search_query)
            if matches:
                for idx, snippet in enumerate(matches[:10], start=1):
                    st.write(f"{idx}. {snippet}")
            else:
                st.warning("No matching text was found in the uploaded manual for that keyword.")
        else:
                st.warning("No searchable text was found for this equipment documentation yet.")
    else:
        st.caption("Enter a keyword to search the uploaded manual content.")

    st.markdown("---")
    st.subheader("Future AI Manual Search")
    st.info("Placeholder only: a future local AI feature may search verified equipment documentation. No clinical decisions, treatment recommendations, or external AI calls are implemented.")
    st.text_area("Ask about this equipment documentation", placeholder="Example: What are the setup steps?", disabled=True)


def main() -> None:
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    if "selected_machine_id" not in st.session_state:
        st.session_state["selected_machine_id"] = None

    if "scanner_active" not in st.session_state:
        st.session_state["scanner_active"] = False

    handle_machine_query_parameter()

    with st.sidebar:
        st.title("Menu")
        for page_name in ["Home", "Library", "Admin Upload"]:
            if st.button(page_name, key=f"nav_{page_name}"):
                st.query_params.clear()
                st.session_state["current_page"] = page_name
                st.session_state["scanner_active"] = False
                if page_name != "Equipment Page":
                    st.session_state["selected_machine_id"] = None

    current_page = st.session_state["current_page"]

    if current_page == "Home":
        render_home()
    elif current_page == "Library":
        render_library()
    elif current_page == "Admin Upload":
        render_admin_upload()
    else:
        if st.session_state.get("selected_machine_id"):
            render_machine_page(st.session_state["selected_machine_id"])
        else:
            st.warning("No equipment selected. Please choose equipment from the Library or scan a QR code from Home.")


if __name__ == "__main__":
    main()
