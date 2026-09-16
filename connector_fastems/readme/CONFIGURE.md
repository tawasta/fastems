## Backend

**MMS Integration \> Backends \> New**

* **Name** - descriptive name, e.g. `MMS Production`
* **API URL** - base address of the MMS server's REST API
* **Auth Method** - `HTTP Basic` or `ApiKey`
* **Username / Password** - credentials for HTTP Basic authentication
* **API Key** - key for ApiKey authentication
* **Export Production Orders** - enable automatic export of production orders
* **Import Production Reports** - enable automatic import of manufacturing reports
* **Report Batch Size** - number of reports fetched per polling cycle (default: 100)

Click **Test Connection** to verify connectivity - every attempt is
logged to `api.request` (*Settings \> Technical \> API Requests*) whether
it succeeds or fails.

## Binding

**MMS Integration \> Production Order Bindings \> New**

* **Manufacturing Order** - the Odoo production order (must already have a **Deadline** set)
* **Backend** - the MMS backend to use
* **MMS Order Number** - OrderNumber in MMS, usually the same as the Odoo order name
* **MMS Part Master Data** - part name in MMS (max 25 characters), must already exist in MMS
* **MMS Order Status** - `Released` or `Urgent`

Work orders are matched to the MMS `OperationNumber` first by workcenter
name (a workcenter whose name ends with the operation number, e.g.
`"Fms 5 - 10"` matches op `10`), falling back to positional order
(op `10` -\> 1st work order, op `20` -\> 2nd, and so on).
