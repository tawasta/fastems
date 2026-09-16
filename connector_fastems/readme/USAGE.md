Export (POST)
-------------

Create a binding, then either wait for the **MMS: Export Production
Orders** cron (every 10 minutes) or click **Export to MMS** on the
binding. On success `sync_state` becomes `done`.

Update (PUT)
------------

If the Manufacturing Order's quantity, dates or status change after
export, click **Update in MMS** on the binding. This is a manual action
only - there is no automatic trigger on Manufacturing Order changes.

Delete (DELETE)
---------------

Click **Delete from MMS** on the binding. MMS rejects the deletion if
any parts are currently in progress for the order.

Import reports (GET)
---------------------

The **MMS: Get manufacturing reports** cron (every 5 minutes) fetches
new reports and updates the matching binding's work orders using
standard Odoo button methods.
