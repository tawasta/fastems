.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

=====================
Fastems MMS Connector
=====================

Odoo 17 module that integrates Odoo with **Fastems MMS** (Manufacturing
Management Software) via its REST API (MMS-3010 ERP Interface). Production
orders created in Odoo are sent to MMS, and MMS reports manufacturing
progress back to Odoo so work order states stay up to date without manual
data entry.

Part master data (which parts exist, their operations) is expected to
already exist in MMS - this module does not import or export part master
data, only production orders and their manufacturing progress.

Features
========

* Export production orders to MMS: create (``POST``), update (``PUT``)
  and delete (``DELETE``) ``/erp/orders/productionorder``
* Import manufacturing reports from MMS (``GET /erp/reports/bufferdata``)
  and update ``mrp.workorder``/``mrp.production`` state accordingly
* Two authentication modes, matching MMS's OpenAPI spec:

  * **HTTP Basic Authentication**
  * **ApiKey Authentication** (sent as the ``APIKey`` HTTP header)

* "Test Connection" tool for validating configuration
* Every API request/response is logged to ``api.request`` (via the shared
  ``api_request_handler`` module) for debugging and audit
* Manufacturing Orders must have a Deadline set before they can be bound
  to MMS, since MMS requires a due date on every production order

Architecture
============

* ``mms.backend`` - connection settings (URL, authentication), cron
  trigger methods, and the "Test Connection" action. Inherits the shared
  ``api.request.mixin`` (``api_request_handler``) for the actual HTTP call
  and request/response logging; ``mms_api_request_mixin.py`` adds only the
  MMS-specific URL/header/auth construction on top of it.
* ``mms.binding.mixin`` - abstract base providing external ID tracking
  and sync state management, shared by any Odoo↔MMS binding model
* ``mms.production.order.binding`` - the concrete binding between
  ``mrp.production`` and MMS, implementing the export/update/delete
  methods and report processing
* Crons are triggers only - all actual work runs as ``queue_job`` jobs,
  enabling retries and error visibility

Security
========

``mms.backend`` stores API credentials (username/password and/or API
key), so it is readable and writable only by administrators
(``base.group_system``). Production Order Bindings are also readable by
regular internal users (``base.group_user``), but only administrators can
create, edit or delete them.

Configuration
=============

Backend
-------

**MMS Integration → Backends → New**

* **Name** - descriptive name, e.g. ``MMS Production``
* **API URL** - MMS server address, e.g. ``http://mms-server:8080``
* **Auth Method** - ``HTTP Basic`` or ``ApiKey``
* **Username / Password** - credentials for HTTP Basic authentication
* **API Key** - key for ApiKey authentication
* **Export Production Orders** - enable automatic export of production
  orders
* **Import Production Reports** - enable automatic import of
  manufacturing reports
* **Report Batch Size** - number of reports fetched per polling cycle
  (default: 100)

Click **Test Connection** to verify connectivity - every attempt is
logged to ``api.request`` (*Settings → Technical → API Requests*) whether
it succeeds or fails.

Binding
-------

**MMS Integration → Production Order Bindings → New**

* **Manufacturing Order** - the Odoo production order (must already have
  a **Deadline** set)
* **Backend** - the MMS backend to use
* **MMS Order Number** - OrderNumber in MMS, usually the same as the Odoo
  order name
* **MMS Part Master Data** - part name in MMS (max 25 characters), must
  already exist in MMS
* **MMS Order Status** - ``Released`` or ``Urgent``

Work orders are matched to the MMS ``OperationNumber`` first by workcenter
name (a workcenter whose name ends with the operation number, e.g.
``"Fms 5 - 10"`` matches op ``10``), falling back to positional order
(op ``10`` → 1st work order, op ``20`` → 2nd, and so on).

Usage
=====

* **Export (POST)**: create a binding, then either wait for the
  **MMS: Export Production Orders** cron (every 10 minutes) or click
  **Export to MMS** on the binding. On success ``sync_state`` becomes
  ``done``.
* **Update (PUT)**: if the Manufacturing Order's quantity, dates or
  status change after export, click **Update in MMS** on the binding.
  This is a manual action only.
* **Delete (DELETE)**: click **Delete from MMS** on the binding. MMS
  rejects the deletion if any parts are currently in progress for the
  order.
* **Import reports (GET)**: the **MMS: Get manufacturing reports** cron
  (every 5 minutes) fetches new reports and updates the matching
  binding's work orders using standard Odoo button methods.

Known issues / Roadmap
=======================

* The completed-quantity field to use from ``operation-completed``
  reports (``OrderedAmount`` vs. ``OrderedAmount - ScrappedAmount``) is
  not confirmed against a real MMS environment.
* MMS's own spec notes that a ``200`` response on order endpoints "may
  still have logical errors", with no documented error-body schema for
  that case - such logical failures cannot currently be distinguished
  from a real success.
* Work order matching by workcenter name suffix can in theory match the
  wrong workcenter if its name happens to end with the same digits as an
  operation number.
* Deleting processed report messages from MMS
  (``DELETE /erp/reports/bufferdata``) is not implemented; MMS purges
  them automatically after 3 months by default.

Credits
=======

Contributors
------------

* Valtteri Lattu <valtteri.lattu@futural.fi>

Maintainer
----------

.. image:: https://futural.fi/templates/tawastrap/images/logo.png
   :alt: Futural Oy
   :target: https://futural.fi/

This module is maintained by Futural Oy.
