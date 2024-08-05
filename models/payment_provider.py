import logging
import hmac
import hashlib
import base64
import urllib.parse

from odoo import _, api, fields, models
from odoo.addons.payment_viettelpay import const

_logger = logging.getLogger(__name__)

class PaymentProviderViettelPay(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("viettelpay", "ViettelPay")], ondelete={"viettelpay": "set default"}
    )
    
    viettelpay_merchant_code = fields.Char(string="Merchant Code", required_if_provider="viettelpay")
    viettelpay_hash_secret = fields.Char(string="Hash Key", required_if_provider="viettelpay")
    viettelpay_access_code = fields.Char(string="Access Code", required_if_provider="viettelpay")
    viettelpay_payment_link = fields.Char(string="ViettelPay URL", required_if_provider="viettelpay")
    viettelpay_white_list_ip = fields.Text(string="White List IPs", help="Comma-separated list of allowed IP addresses.")

    @api.model
    def _get_compatible_providers(self, *args, currency_id=None, is_validation=False, **kwargs):
        providers = super()._get_compatible_providers(*args, currency_id=currency_id, is_validation=is_validation, **kwargs)
        currency = self.env["res.currency"].browse(currency_id).exists()
        if (currency and currency.name not in const.SUPPORTED_CURRENCIES) or is_validation:
            providers = providers.filtered(lambda p: p.code != "viettelpay")
        return providers

    def _get_supported_currencies(self):
        supported_currencies = super()._get_supported_currencies()
        if self.code == "viettelpay":
            supported_currencies = supported_currencies.filtered(lambda c: c.name in const.SUPPORTED_CURRENCIES)
        return supported_currencies

    def _get_payment_url(self, params, hash_key):
        access_code = str(self.viettelpay_access_code)
        bill_code = str(params.get("billcode", ""))
        command = str(params.get("command", ""))
        merchant_code = str(self.viettelpay_merchant_code)
        order_id = str(params.get("order_id", ""))
        trans_amount = str(params.get("trans_amount", ""))
        version = str(params.get("version", ""))

        # Create inputData as per the specified format
        input_data = access_code + bill_code + command + merchant_code + order_id + trans_amount + version

        # Generate checksum using HMAC-SHA1
        checksum = self.__hmacsha1(hash_key, input_data)
        
        # Build query string
        input_data_sorted = sorted(params.items())
        query_string = ""
        for seq, (key, val) in enumerate(input_data_sorted):
            if seq > 0:
                query_string += "&"
            query_string += f"{key}={urllib.parse.quote_plus(str(val))}"
        
        # Return the full payment URL with checksum
        return f"{self.viettelpay_payment_link}?{query_string}&check_sum={checksum}"

    def _get_default_payment_method_codes(self):
        default_codes = super()._get_default_payment_method_codes()
        if self.code != "viettelpay":
            return default_codes
        return const.DEFAULT_PAYMENT_METHODS_CODES

    @staticmethod
    def __hmacsha1(hash_key, data):
        byte_key = hash_key.encode("ascii")
        byte_data = data.encode("ascii")
        
        # Compute HMAC-SHA1 hash
        hmac_result = hmac.new(byte_key, byte_data, hashlib.sha1).digest()
        
        # Base64 encode the result
        base64_encoded_result = base64.b64encode(hmac_result).decode('ascii')
        
        # URL-encode the Base64 encoded result
        url_encoded_result = urllib.parse.quote_plus(base64_encoded_result)
        
        return url_encoded_result
