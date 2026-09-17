import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# The MMS report statuses that trigger updates in Odoo
_REPORT_STATE_MAP = {
    "operation-started": "progress",
    "parts-produced": "progress",
    "operation-completed": "done",
}

# Report discriminators that are only logged on the chatter, since they
# don't map to a single mrp.workorder state change.
_REPORT_LOG_ONLY = {"parts-scrapped", "parts-modified"}

# states in ascending order
_STATE_ORDER = ["pending", "waiting", "ready", "progress", "done", "cancel"]


class MmsProductionOrderBinding(models.Model):
    """
    MMS Production Order Binding between Odoo and MMS orders

    Done:
    - POST / PUT / DELETE for production orders from Odoo to MMS
    - GET production reports from MMS and update work orders in Odoo
    """

    _name = "mms.production.order.binding"
    _description = "MMS Production Order Binding"
    _inherit = "mms.binding.mixin"

    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Manufacturing Order",
        required=True,
        ondelete="cascade",
    )

    mms_order_number = fields.Char(
        string="MMS Order Number",
        required=True,
        help=(
            "The OrderNumber value used in MMS. "
            "Must match the OrderNumber in MMS report messages exactly. "
            "Defaults to the Odoo production order name."
        ),
    )

    mms_part_master_data = fields.Char(
        string="MMS Part Master Data Name",
        required=True,
        size=25,
        help=(
            "PartMasterData name in MMS (max 25 characters, per MMS's "
            "ErpPartMasterData/ErpCreateOrder schemas). "
            "The part must already exist in MMS before the order is sent."
        ),
    )

    mms_order_status = fields.Selection(
        selection=[
            ("Released", "Released"),
            ("Urgent", "Urgent"),
        ],
        string="MMS Order Status",
        default="Released",
        required=True,
    )

    _sql_constraints = [
        (
            "unique_production_backend",
            "UNIQUE(production_id, backend_id)",
            "A production order can only have one binding per MMS backend.",
        ),
        (
            "unique_order_number_backend",
            "UNIQUE(mms_order_number, backend_id)",
            "MMS OrderNumber must be unique per backend.",
        ),
    ]

    @api.constrains("production_id")
    def _check_production_has_deadline(self):
        """
        DueDate is a required field on MMS's ErpCreateOrder (POST
        /erp/orders/productionorder) - a binding cannot be exported without
        it, so require it here instead of only failing on export.
        """
        for binding in self:
            if not binding.production_id.date_deadline:
                raise ValidationError(
                    _(
                        "Manufacturing Order %(name)s has no Deadline set. "
                        "MMS requires a due date for every production order, "
                        "so a Deadline must be set before it can be bound to "
                        "an MMS backend.",
                        name=binding.production_id.name,
                    )
                )

    def export_to_mms(self):
        """
        Queue job: POST this production order to MMS.

        Only runs if mms_id is not yet set (i.e. not yet created in MMS).
        """
        self.ensure_one()
        if not self.integration_active:
            _logger.info("Binding %s: integration inactive – skipping.", self.id)
            return
        if self.mms_id:
            _logger.info(
                "Binding %s: already synced to MMS (mms_id=%s) – skipping POST.",
                self.id,
                self.mms_id,
            )
            return

        try:
            payload = self._build_order_payload()
            response = self.backend_id._make_request(
                "POST",
                "/erp/orders/productionorder",
                json=payload,
            )
            if not response:
                self._set_sync_error(_("Could not reach the MMS API."))
                return
            if response.status_code == 200:
                self._set_sync_done(mms_id=self.mms_order_number)
                _logger.info(
                    "MMS: production order %s created (OrderNumber=%s).",
                    self.production_id.name,
                    self.mms_order_number,
                )
        except Exception as exc:
            _logger.exception(
                "MMS: POST production order failed for binding %s.", self.id
            )
            self._set_sync_error(str(exc))
            raise

    def update_in_mms(self):
        """
        Queue job: PUT this production order's current data to MMS.

        Only makes sense once the order already exists in MMS (mms_id set).
        Triggered manually via action_update_in_mms() when the underlying
        Manufacturing Order's quantity/dates/status have changed after the
        initial export.
        """
        self.ensure_one()
        if not self.integration_active:
            _logger.info("Binding %s: integration inactive – skipping.", self.id)
            return
        if not self.mms_id:
            _logger.info(
                "Binding %s: not yet created in MMS – use export instead of update.",
                self.id,
            )
            return

        try:
            payload = self._build_order_payload()
            response = self.backend_id._make_request(
                "PUT",
                "/erp/orders/productionorder",
                json=payload,
            )
            if not response:
                self._set_sync_error(_("Could not reach the MMS API."))
                return
            if response.status_code == 200:
                self._set_sync_done(mms_id=self.mms_order_number)
                _logger.info(
                    "MMS: production order %s updated (OrderNumber=%s).",
                    self.production_id.name,
                    self.mms_order_number,
                )
        except Exception as exc:
            _logger.exception(
                "MMS: PUT production order failed for binding %s.", self.id
            )
            self._set_sync_error(str(exc))
            raise

    def action_update_in_mms(self):
        """Manual button: enqueue a PUT job for selected bindings."""
        for record in self:
            record.with_delay().update_in_mms()

    def delete_from_mms(self):
        """
        Queue job: DELETE this production order from MMS.

        MMS validation: no parts may be in progress for the order.
        After successful deletion the binding's mms_id is cleared so it
        can be re-created if needed.
        """
        self.ensure_one()
        if not self.mms_id:
            _logger.info(
                "Binding %s: no mms_id set – nothing to delete in MMS.", self.id
            )
            return

        try:
            response = self.backend_id._make_request(
                "DELETE",
                "/erp/orders/productionorder",
                params={
                    "orderNumber": self.mms_order_number,
                    "partMasterDataName": self.mms_part_master_data,
                },
            )
            if not response:
                self._set_sync_error(_("Could not reach the MMS API."))
                return
            if response.status_code == 200:
                _logger.info(
                    "MMS: production order %s deleted from MMS.", self.mms_order_number
                )
                self.write(
                    {
                        "mms_id": False,
                        "sync_state": "pending",
                        "sync_error": False,
                    }
                )
        except Exception as exc:
            _logger.exception(
                "MMS: DELETE production order failed for binding %s.", self.id
            )
            self._set_sync_error(str(exc))
            raise

    def action_delete_from_mms(self):
        """Manual button: enqueue a DELETE job for selected bindings."""
        for record in self:
            record.with_delay().delete_from_mms()

    def _build_order_payload(self):
        """
        Build the JSON body for POST/PUT /erp/orders/productionorder.

        DueDate is required by MMS for POST (ErpCreateOrder).
        _check_production_has_deadline() enforces this when the binding is
        created/written, but the deadline could still be cleared on the
        Manufacturing Order afterwards, so it is checked again here too.
        """
        production = self.production_id
        if not production.date_deadline:
            raise ValidationError(
                _(
                    "Manufacturing Order %(name)s has no Deadline set. MMS "
                    "requires a due date for every production order.",
                    name=production.name,
                )
            )
        payload = {
            "OrderNumber": self.mms_order_number,
            "PartMasterData": self.mms_part_master_data,
            "Amount": int(production.product_qty),
            "OrderStatus": self.mms_order_status,
            # Odoo datetime fields are stored as naive UTC; MMS requires full
            # ISO8601 with an explicit offset, so mark it as UTC with "Z".
            "DueDate": production.date_deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if production.date_start:
            payload["EarliestStart"] = production.date_start.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if production.origin:
            payload["Description"] = production.origin
        return payload

    def _process_mms_report(self, backend, report):
        """
        Dispatch a single MMS report message to the correct work order.

        :param backend:  mms.backend record
        :param report:   dict – one element from the MMS Reports[] array
        """
        discriminator = report.get("discriminator", "")
        # PartsModifiedReport has no "OrderNumber" - it reports a move from
        # OriginalOrderNumber to NewOrderNumber, so the binding is looked up
        # by the original order.
        if discriminator == "parts-modified":
            order_number = report.get("OriginalOrderNumber", "")
        else:
            order_number = report.get("OrderNumber", "")
        operation_number = str(report.get("OperationNumber", ""))
        message_number = report.get("MessageNumber")

        _logger.info(
            "MMS report #%s: discriminator=%s  order=%s  op=%s",
            message_number,
            discriminator,
            order_number,
            operation_number,
        )

        # Find the binding by MMS order number
        binding = self.search(
            [
                ("mms_order_number", "=", order_number),
                ("backend_id", "=", backend.id),
            ],
            limit=1,
        )
        if not binding:
            _logger.warning(
                "MMS report #%s: no binding for OrderNumber=%s – skipping.",
                message_number,
                order_number,
            )
            return

        production = binding.production_id

        if discriminator == "orders-completed":
            binding._handle_order_completed(production, report)
            return

        if discriminator in _REPORT_LOG_ONLY:
            binding._log_mms_report(production, discriminator, report)
            return

        # Ignore report types that don't map to a state change
        if discriminator not in _REPORT_STATE_MAP:
            _logger.debug(
                "MMS report #%s: discriminator '%s' – no state change needed.",
                message_number,
                discriminator,
            )
            return

        # Find the matching work order by MMS OperationNumber
        target_state = _REPORT_STATE_MAP[discriminator]
        workorder = binding._find_workorder(production, operation_number)
        if not workorder:
            _logger.warning(
                "MMS report #%s: no workorder for op=%s on %s – skipping.",
                message_number,
                operation_number,
                production.name,
            )
            return

        # Apply the state update
        binding._apply_workorder_state(workorder, target_state, report)

    def _find_workorder(self, production, operation_number):
        """
        Return the mrp.workorder that corresponds to the MMS OperationNumber.

        Matching is attempted in two passes:
          The work order's workcenter name ends with the integer op (operation) number
          (e.g. workcenter "Siemens 840D - 10" matches op 10).

          Positional fallback: op 10 → index 0, op 20 → index 1, …
          (assumes operations are numbered 10, 20, 30 ... in MMS).
        """
        if not operation_number:
            return None

        try:
            op_int = int(operation_number)
        except ValueError:
            _logger.error(
                "MMS OperationNumber '%s' is not an integer – cannot match workorder.",
                operation_number,
            )
            return None

        workorders = production.workorder_ids.sorted("id")

        # workcenter name ends with the op number
        for wo in workorders:
            if wo.workcenter_id.name.strip().endswith(str(op_int)):
                _logger.debug(
                    "MMS op %s: matched workorder '%s' via workcenter name.",
                    op_int,
                    wo.name,
                )
                return wo

        # positional index fallback
        index = (op_int // 10) - 1
        workorder_list = list(workorders)
        if 0 <= index < len(workorder_list):
            matched = workorder_list[index]
            _logger.debug(
                "MMS op %s: positional match → index %d ('%s').",
                op_int,
                index,
                matched.name,
            )
            return matched

        return None

    def _apply_workorder_state(self, workorder, target_state, report):
        """
        Advance an mrp.workorder to target_state.

        Rules:
          - Only forward moves are allowed (no regression).
          - Uses standard Odoo button methods so all business logic
            (time tracking, qty updates) runs as normal.
          - When moving to 'done', writes the produced qty from the MMS report
            if available.
        """
        current = workorder.state

        try:
            current_idx = _STATE_ORDER.index(current)
            target_idx = _STATE_ORDER.index(target_state)
        except ValueError:
            _logger.error(
                "Unknown state: current=%s target=%s (workorder %s)",
                current,
                target_state,
                workorder.id,
            )
            return

        if target_idx <= current_idx:
            _logger.debug(
                "Workorder %s already at '%s' (≥ target '%s') – skipping.",
                workorder.id,
                current,
                target_state,
            )
            return

        _logger.info(
            "MMS: workorder %s ('%s') on %s: %s → %s",
            workorder.id,
            workorder.name,
            workorder.production_id.name,
            current,
            target_state,
        )

        if target_state == "progress":
            # Ensure the work order is startable first
            if current in ("pending", "waiting"):
                workorder.write({"state": "ready"})
            workorder.button_start()

        elif target_state == "done":
            # "done" is only reached via OperationCompletedReport, which has
            # no "Amount" field - only OrderedAmount and ScrappedAmount, so
            # the produced qty must subtract scrap to avoid overcounting.
            qty = report.get("Amount")
            if qty is None and report.get("OrderedAmount") is not None:
                qty = report.get("OrderedAmount") - (report.get("ScrappedAmount") or 0)
            if qty:
                workorder.write({"qty_production": int(qty)})
            # Must be in progress before finishing
            if workorder.state != "progress":
                if workorder.state in ("pending", "waiting"):
                    workorder.write({"state": "ready"})
                workorder.button_start()
            workorder.button_finish()

    def _handle_order_completed(self, production, report):
        """
        Called when MMS sends 'orders-completed'.

        Attempts to mark the mrp.production as done only when all its
        work orders are already in state 'done'.
        """
        if production.state not in ("confirmed", "progress", "to_close"):
            _logger.debug(
                "orders-completed for %s but production state is '%s' – skipping.",
                production.name,
                production.state,
            )
            return

        pending = production.workorder_ids.filtered(lambda w: w.state != "done")
        if pending:
            _logger.warning(
                "MMS orders-completed for %s but %d workorder(s) still not done: %s",
                production.name,
                len(pending),
                ", ".join(pending.mapped("name")),
            )
            return

        _logger.info("MMS orders-completed: closing production %s.", production.name)
        production.button_mark_done()

    def _log_mms_report(self, production, discriminator, report):
        """
        Post a chatter message for report types that don't map to a single
        workorder state change (parts-scrapped, parts-modified), so the
        information from MMS isn't silently dropped.
        """
        if discriminator == "parts-scrapped":
            message = _(
                "Fastems MMS: %(amount)s part(s) scrapped on operation %(op)s."
                " Reason: %(reason)s. %(info)s",
                amount=report.get("Amount"),
                op=report.get("OperationNumber"),
                reason=report.get("ScrapReason") or _("not specified"),
                info=report.get("ScrapInfo") or "",
            )
        elif discriminator == "parts-modified":
            message = _(
                "Fastems MMS: %(qty)s part(s) moved from order %(orig_order)s /"
                " operation %(orig_op)s to order %(new_order)s / operation"
                " %(new_op)s.",
                qty=report.get("ModifiedQuantity"),
                orig_order=report.get("OriginalOrderNumber"),
                orig_op=report.get("OriginalOperationNumber"),
                new_order=report.get("NewOrderNumber"),
                new_op=report.get("NewOperationNumber"),
            )
        else:
            return

        _logger.info(
            "MMS report #%s: %s (%s)",
            report.get("MessageNumber"),
            discriminator,
            message,
        )
        production.message_post(body=message)
