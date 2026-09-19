# How to use QR Item Manager

Start with one item and follow the steps below. Your changes are stored on the
computer running the app.

## 1. Set up your fields

Open **Admin Panel → Field Settings**. Enter a field name, choose its type, and
press **Save** on that row. Press **Add** to create another field. If no rows
are shown, press **Add** first.

- **Save:** Save each field after entering or changing its name, type, or date
  format. **Unsaved** means the changes have not been saved yet. **Saved ✓**
  appears after a successful save and stays until the next interaction. Saving
  one field does not save changes to other fields.
- **Remove:** Remove a field you no longer need. A confirmation appears because
  removing a field also deletes its saved values from every record. Choose
  **YES** to remove it, or **NO** to keep it.

For example:

| Field name | Type | Example value |
| --- | --- | --- |
| ItemName | Text / Number | Digital microscope |
| Location | Text / Number | Lab A |
| CheckDate | Date | Pick a date from the calendar |

You can have up to **six fields**, with names up to **ten characters** long.
Use a different name for each field; **Record ID** and **QR Code** are reserved.
These field settings apply to every item in this installation.
For Date fields, choose **DD/MM/YYYY**, **MM/DD/YYYY**, or **YYYY/MM/DD** before
saving the field settings.

## 2. Add an item

Open **Manage** and press **Add**. A new row appears with an automatic Record ID,
such as `REC-0001`. Click that ID to open **Record Details**.

IDs may have gaps if earlier records were deleted. Keep the assigned ID: it is
the permanent reference used by that item's QR label. The four-digit format is
a minimum width, not a limit: `REC-9999` is followed by `REC-10000`.

## 3. Enter and save details

Fill in the fields and press **Save** beside each edited value. A date field opens
a calendar. **Saved ✓** confirms the save; **Unsaved** means that field still has
changes to save. Saving one field does not save the other fields.

**Last updated** shows the last saved record change in UTC. If you try to leave
using **DONE** or the sidebar with unsaved edits, choose **Stay** to keep editing
or **Leave** to discard those edits.

If a date field shows **Previous saved text**, its old value could not be read
as a stored date. Choose the intended date and **Save** to replace it. To remove
that old value instead, select **Clear saved value** and press **Save**. The old
value stays saved until you take one of these actions.

## 4. Generate and print the QR label

In the QR panel on Record Details, press **Generate QR**. Save at least one
nonblank field value first, and save any remaining edits to enable this button.

- **Download QR** saves the QR as a PNG image.
- **Print QR label** opens a preview. Choose **40, 50, or 60 mm**, then press
  **Print label**, or use **Download label PDF**.
- Print at **Actual size / 100%**, with browser headers and footers off. Use the
  matching paper size and check one printed label before printing a batch.

Press **DONE** to return to Manage.

## 5. Scan and view an item

Open **Home**, press the round **Scan QR** button, and allow camera access when
asked. Hold the label inside the square preview until it is read. The app opens
the matching record in **Library** and stops the camera.

After checking the details, press **Scan another QR** beside **Back to Library**
to open the scanner immediately and check the next item.

Use **Stop Scanner** to cancel scanning. You can also open **Library** from the
sidebar, search for an item, and click its Record ID without using a camera.

The QR stores only its Record ID. Scanning it with a general phone camera may
show text instead of opening a page; scan through this app to view its details.

## 6. Update an existing item

From a Library record, press **Edit Record** to open its editable details. Change a
value and press that field's **Save** button. The item's ID stays the same, so
its existing QR label continues to work while the QR remains active.

If all saved values are cleared, the QR resets to **Not available**. Save a value
and press **Generate QR** again to reactivate it.

## 7. Back up your data

Open **Admin Panel → Backup & Restore**.

1. Press **Create backup**.
2. Press **Download backup ZIP** and keep the file somewhere safe.
3. After saving more changes, create a new backup to include them.

The ZIP includes saved records, IDs, field settings, dates, timestamps, and active
QR images. Unsaved edits are not included.

### Restore a backup

Upload a backup ZIP in the Restore section and check the displayed counts.
Press **Review restore**, then **Restore and replace** only when you want to
replace the current records and field settings. **Cancel** keeps the current data.

Before replacement, the app automatically saves a copy of the current saved data.
Use **Download previous data** in the same section to download that copy. You can
upload it through Restore to recover the previous state. Restore replaces data;
it does not combine the current records with the uploaded records.

## Quick help

| What you see | What to do |
| --- | --- |
| Camera is dark or paused | Check camera permission and the selected camera. Click **Show camera** if offered. In Brave, also check the site's **Autoplay** permission. |
| No camera video arrives | Choose another camera or press **Try again** when offered. |
| Generate QR is disabled | Save at least one nonblank value and save any edited fields. |
| Camera access needs HTTPS or localhost | On the computer running the app, use its Local URL (default `http://localhost:8502`). Scanning from another device requires an HTTPS address for the app; that device's `localhost` refers to itself. |
| QR is not active | Find the item in Manage, save a value if needed, and generate its QR again. If the record does not exist in this installation, check that you opened the correct app and data folder. |
| An old date appears as saved text | Choose the intended date in the calendar and Save. The app does not guess ambiguous dates such as `1/2/94`. |
| A search finds no records | Clear the search, or try the Record ID, an item value, or the date in its displayed format. |

**Deleting data:** **Del** removes a record after confirmation. Removing a field
in Admin Panel also deletes that field's values from every record. Download a
backup first if you may need to recover them later.

Library provides a read-only view, but the app does not have user permissions:
anyone with app access can still open Manage and Admin Panel.

Unsaved-change prompts apply to navigation inside the app. Save before refreshing
the browser or closing the tab; those actions are not protected by the prompt.
