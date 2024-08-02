import logging
import urllib.parse
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.payment_viettelpay.controllers.main import ViettelPayController

_logger = logging.getLogger(__name__)

class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "viettelpay":
            return res

        base_url = self.provider_id.get_base_url()
        int_amount = int(self.amount)

        try:
            params = {
                "version": "2.0",
                "command": "PAYMENT",
                "merchant_code": "DEMONT",
                "order_id": self.reference,
                "trans_amount": int_amount,
                "billcode": self.reference,
                "return_url": urllib.parse.urljoin(base_url, ViettelPayController._return_url),
                "locale": "Vi",
                "desc": f"Thanh toán đơn hàng {self.reference}",
            }

            # Log các giá trị params để kiểm tra
            _logger.info("ViettelPay params: %s", params)

            checksum_str = (
                str(self.provider_id.viettelpay_access_code) +
                str(params["billcode"]) +
                str(params["command"]) +
                str(params["merchant_code"]) +
                str(params["order_id"]) +
                str(params["trans_amount"]) +
                str(params["version"])
            )

            payment_link_data = self.provider_id._get_payment_url(
                params=params, hash_key=self.provider_id.viettelpay_hash_secret
            )

            rendering_values = {
                "api_url": "https://sandbox.viettelmoney.vn/PaymentGateway/payment",
                "billcode": params["billcode"],
                "command": params["command"],
                "desc": params["desc"],
                "locale": params["locale"],
                "merchant_code": params["merchant_code"],
                "order_id": params["order_id"],
                "return_url": params["return_url"],
                "trans_amount": params["trans_amount"],
                "version": params["version"],
                "check_sum": payment_link_data.split('check_sum=')[1],  # Assuming the check_sum is the last part of the URL
            }
            return rendering_values

        except Exception as e:
            _logger.error("Error while generating payment link: %s", str(e))
            raise ValidationError(_("Error while generating payment link: %s") % str(e))

    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        reference = notification_data.get('order_id')
        if not reference:
            raise ValidationError(_("Notification data does not contain reference (order_id)"))
        
        tx = self.sudo().search([('reference', '=', reference), ('provider_code', '=', provider_code)], limit=1)
        if not tx:
            raise ValidationError(_("Transaction not found for reference: %s") % reference)
        
        return tx

    def _process_notification_data(self, notification_data):
        if not notification_data:
            raise ValidationError(_("No notification data received"))
        
        amount = notification_data.get('trans_amount')
        if not amount or float(amount) != self.amount:
            raise ValidationError(_("Transaction amount does not match or is missing"))
        
        reference = notification_data.get('order_id')
        if not reference:
            raise ValidationError(_("Notification data does not contain reference (order_id)"))
        
        self.provider_reference = reference
        # Additional processing logic as needed
        # For example, check payment status and update transaction state
