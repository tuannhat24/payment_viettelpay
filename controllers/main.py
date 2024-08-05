import logging
import urllib.parse
import pprint
import hmac
import hashlib

from odoo import http, _
from odoo.http import request
from werkzeug.exceptions import Forbidden
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class ViettelPayController(http.Controller):
    _return_url = "/payment/viettelpay/return"
    _cancel_url = "/payment/viettelpay/cancel"
    _ipn_url = "/payment/viettelpay/webhook"
    _result_url = "/payment/viettelpay/result"

    @http.route(_return_url, type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def viettelpay_return_from_checkout(self, **data):
        _logger.info("Xử lý chuyển hướng từ ViettelPay với dữ liệu: %s", data)

        # Chuyển hướng đến URL kết quả với dữ liệu cần thiết
        return request.redirect(f"/payment/viettelpay/result?{urllib.parse.urlencode(data)}")

    @http.route(_cancel_url, type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def viettelpay_cancel_from_checkout(self, **data):
        _logger.info("Xử lý hủy từ ViettelPay với dữ liệu: %s", data)

        # Chuyển hướng đến URL kết quả với dữ liệu cần thiết
        return request.redirect(f"/payment/viettelpay/result?{urllib.parse.urlencode(data)}")

    @http.route(_ipn_url, type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def viettelpay_webhook(self, **data):
        ip_address = request.httprequest.environ.get("REMOTE_ADDR")
        _logger.info("Nhận thông báo từ ViettelPay với dữ liệu:\n%s\nTừ IP: %s", pprint.pformat(data), ip_address)

        white_list_ip = http.request.env["payment.provider"].sudo().search([("code", "=", "viettelpay")], limit=1).viettel_white_list_ip
        white_list_ip = white_list_ip.replace(" ", "").split(";")

        if ip_address not in white_list_ip:
            _logger.warning("Nhận thông báo từ địa chỉ IP không được ủy quyền: %s", ip_address)
            return request.make_json_response({"RspCode": "99", "Message": "Lỗi không xác định"})

        try:
            tx_sudo = request.env["payment.transaction"].sudo()._get_tx_from_notification_data("viettelpay", data)
            self._verify_notification_signature(data, tx_sudo)
            tx_sudo._handle_notification_data("viettelpay", data)
        except Forbidden:
            _logger.warning("Lỗi Forbidden trong quá trình xác minh chữ ký. Dừng lại.", exc_info=True)
            tx_sudo._set_error("ViettelPay: " + _("Nhận dữ liệu với chữ ký không hợp lệ."))
            return request.make_json_response({"RspCode": "02", "Message": "Check sum không chính xác"})
        except AssertionError:
            _logger.warning("Lỗi Assertion trong quá trình xử lý thông báo. Dừng lại.", exc_info=True)
            tx_sudo._set_error("ViettelPay: " + _("Nhận dữ liệu với số tiền không hợp lệ."))
            return request.make_json_response({"RspCode": "03", "Message": "Tài khoản VTP không đủ điều kiện thanh toán"})
        except ValidationError:
            _logger.warning("Không thể xử lý dữ liệu thông báo. Dừng lại.", exc_info=True)
            return request.make_json_response({"RspCode": "01", "Message": "Định dạng dữ liệu không hợp lệ"})

        if tx_sudo.state in ["done", "cancel", "error"]:
            _logger.warning("Nhận thông báo cho giao dịch đã được xử lý. Dừng lại.")
            return request.make_json_response({"RspCode": "99", "Message": "Lỗi không xác định"})

        responseCode = data.get("viettel_ResponseCode")

        if responseCode == "00":
            _logger.info("Nhận thông báo thanh toán thành công từ ViettelPay, lưu lại.")
            tx_sudo._set_done()
            _logger.info("Giao dịch thanh toán hoàn tất.")
        elif responseCode == "24":
            _logger.warning("Nhận thông báo hủy thanh toán từ ViettelPay, hủy bỏ.")
            tx_sudo._set_canceled(state_message=_("Khách hàng đã hủy thanh toán."))
            _logger.info("Giao dịch thanh toán đã bị hủy.")
        else:
            _logger.warning("Nhận thông báo thanh toán từ ViettelPay với mã phản hồi không hợp lệ: %s", responseCode)
            tx_sudo._set_error("ViettelPay: " + _("Nhận dữ liệu với mã phản hồi không hợp lệ: %s", responseCode))
            _logger.info("Giao dịch thanh toán thất bại.")
        return request.make_json_response({"RspCode": "00", "Message": "Truy vấn thành công"})

    @http.route(_result_url, type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def viettelpay_result(self, **data):
        _logger.info("Hiển thị kết quả giao dịch với dữ liệu: %s", data)
        return request.render("payment_viettelpay.payment_result", data)

    @staticmethod
    def _verify_notification_signature(data, tx_sudo):
        if not data:
            _logger.warning("Nhận thông báo với dữ liệu thiếu.")
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
            _logger.warning("Nhận thông báo với chữ ký không hợp lệ.")
            raise Forbidden()

    @staticmethod
    def __hmacsha512(key, data):
        byteKey = key.encode("utf-8")
        byteData = data.encode("utf-8")
        return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()
