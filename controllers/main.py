import logging
import urllib.parse
import pprint

from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class ViettelPayController(http.Controller):
    _return_url = "/payment/viettelpay/return"
    _ipn_url = "/payment/viettelpay/webhook"

    @http.route(_return_url, type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def viettelpay_return_from_checkout(self, **data):
        _logger.info("Handling redirection from ViettelPay with data: %s", data)

        # Construct the payment URL with the data parameters
        payment_link_data = (
            "https://sandbox.viettelmoney.vn/PaymentGateway/payment"
            "?billcode={billcode}&command={command}&desc={desc}&locale={locale}"
            "&merchant_code={merchant_code}&order_id={order_id}&return_url={return_url}"
            "&trans_amount={trans_amount}&version={version}&check_sum={check_sum}"
        ).format(**data)

        # Log the constructed payment link data
        _logger.info("Redirecting to payment link: %s", payment_link_data)
        
        # Redirect to the constructed payment link
        return request.redirect(payment_link_data)

    @http.route(_ipn_url, type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def viettelpay_webhook(self, **data):
        ip_address = request.httprequest.environ.get("REMOTE_ADDR")
        _logger.info("Notification received from ViettelPay with data:\n%s\nFrom IP: %s", pprint.pformat(data), ip_address)

        white_list_ip = http.request.env["payment.provider"].sudo().search([("code", "=", "viettelpay")], limit=1).viettel_white_list_ip
        white_list_ip = white_list_ip.replace(" ", "").split(";")

        if ip_address not in white_list_ip:
            _logger.warning("Received notification from an unauthorized IP address: %s", ip_address)
            return

        try:
            tx_sudo = request.env["payment.transaction"].sudo()._get_tx_from_notification_data("viettelpay", data)
            self._verify_notification_signature(data, tx_sudo)
            tx_sudo._handle_notification_data("viettelpay", data)
        except Forbidden:
            _logger.warning("Forbidden error during signature verification. Aborting.", exc_info=True)
            tx_sudo._set_error("ViettelPay: " + _("Received data with invalid signature."))
            return request.make_json_response({"RspCode": "97", "Message": "Invalid Checksum"})
        except AssertionError:
            _logger.warning("Assertion error during notification handling. Aborting.", exc_info=True)
            tx_sudo._set_error("ViettelPay: " + _("Received data with invalid amount."))
            return request.make_json_response({"RspCode": "04", "Message": "Invalid amount"})
        except ValidationError:
            _logger.warning("Unable to handle the notification data. Aborting.", exc_info=True)
            return request.make_json_response({"RspCode": "01", "Message": "Order Not Found"})

        if tx_sudo.state in ["done", "cancel", "error"]:
            _logger.warning("Received notification for already processed transaction. Aborting.")
            return request.make_json_response({"RspCode": "02", "Message": "Order already confirmed"})

        responseCode = data.get("viettel_ResponseCode")

        if responseCode == "00":
            _logger.info("Received successful payment notification from ViettelPay, saving.")
            tx_sudo._set_done()
            _logger.info("Payment transaction completed.")
        elif responseCode == "24":
            _logger.warning("Received canceled payment notification from ViettelPay, canceling.")
            tx_sudo._set_canceled(state_message=_("The customer canceled the payment."))
            _logger.info("Payment transaction canceled.")
        else:
            _logger.warning("Received payment notification from ViettelPay with invalid response code: %s", responseCode)
            tx_sudo._set_error("ViettelPay: " + _("Received data with invalid response code: %s", responseCode))
            _logger.info("Payment transaction failed.")
        return request.make_json_response({"RspCode": "00", "Message": "Confirm Success"})

    @staticmethod
    def _verify_notification_signature(data, tx_sudo):
        if not data:
            _logger.warning("Received notification with missing data.")
            raise Forbidden()

        receive_signature = data.get("viettel_SecureHash")

        if data.get("viettel_SecureHash"):
            data.pop("viettel_SecureHash")
        if data.get("viettel_SecureHashType"):
            data.pop("viettel_SecureHashType")

        inputData = sorted(data.items())
        hasData = ""
        seq = 0
        for key, val in inputData:
            if str(key).startswith("viettel_"):
                if seq == 1:
                    hasData = hasData + "&" + str(key) + "=" + urllib.parse.quote_plus(str(val))
                else:
                    seq = 1
                    hasData = str(key) + "=" + urllib.parse.quote_plus(str(val))

        expected_signature = ViettelPayController.__hmacsha512(tx_sudo.provider_id.viettel_hash_secret, hasData)

        if not hmac.compare_digest(receive_signature, expected_signature):
            _logger.warning("Received notification with invalid signature.")
            raise Forbidden()

    @staticmethod
    def __hmacsha512(key, data):
        byteKey = key.encode("utf-8")
        byteData = data.encode("utf-8")
        return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()
