Fastems MMS controls the FMS cell. Production orders created in Odoo are
sent to MMS so the cell knows what to manufacture, and MMS reports
manufacturing progress back to Odoo so work order states stay up to date
without manual data entry.

Part master data (which parts exist, their operations) is expected to
already exist in MMS - this module does not import or export part master
data, only production orders and their manufacturing progress.

Authentication supports both modes defined in MMS's OpenAPI spec: HTTP
Basic Authentication, and ApiKey Authentication (sent as the `APIKey`
HTTP header). Every API request and response is logged to `api.request`
(via the shared `api_request_handler` module) for debugging and audit.

`mms.backend` stores the API credentials, so it is readable and writable
only by administrators (`base.group_system`). Production Order Bindings
are also readable by regular internal users, but only administrators can
create, edit or delete them.
