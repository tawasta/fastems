from odoo import models


class MmsBackend(models.Model):
    """
    Fastems MMS-specific request building (URL/headers/auth), layered on
    the shared api.request.mixin (api_request_handler) for the actual HTTP
    call and request/response logging (api.request records).
    """

    _inherit = "mms.backend"

    def _build_url(self, endpoint):
        """Construct the full API URL from backend base URL + endpoint."""
        base = (self.api_url or "").rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base}/{endpoint}"

    def _build_headers(self):
        """Return the HTTP headers required for all Fastems MMS API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.auth_method == "apikey" and self.api_key:
            headers["APIKey"] = self.api_key
        return headers

    def _build_auth(self):
        """Return an (username, password) tuple for HTTP Basic auth, or None."""
        if self.auth_method == "basic":
            return (self.api_username or "", self.api_password or "")
        # ApiKey auth is handled via the APIKey header, not HTTP auth.
        return None

    def _make_request(self, method, endpoint, params=None, json=None):
        """
        Execute an HTTP request against the MMS REST API.

        Delegates to api.request.mixin._api_request_make(), which performs
        the call and logs it to api.request (visible under Settings >
        Technical > API Requests) for every attempt, success or failure.

        :param method:   HTTP verb string: 'GET', 'POST', 'PUT', 'DELETE'
        :param endpoint: API path, e.g. '/erp/orders/productionorder'
        :param params:   dict of query parameters
        :param json:     dict payload (serialised to JSON body)
        :returns:        httpx.Response, or False on a transport-level error
        :raises:         odoo.exceptions.ValidationError on a non-2xx response
        """
        self.ensure_one()
        return self._api_request_make(
            method=method,
            endpoint=self._build_url(endpoint),
            headers=self._build_headers(),
            auth=self._build_auth(),
            params=params,
            json=json,
        )
