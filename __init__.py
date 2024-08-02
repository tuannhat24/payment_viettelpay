# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import controllers
from . import models
import logging

from odoo.addons.payment import setup_provider, reset_payment_provider

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    """
    Post-installation hook to set up the ViettelPay payment provider and link payment method.
    """
    # Setup the payment provider for "viettelpay"
    setup_provider(env, "viettelpay")
    
    # Search for the "viettelpay" provider in the "payment.provider" model
    payment_viettelpay = env["payment.provider"].search([("code", "=", "viettelpay")], limit=1)
    
    # Search for the "viettelpay" method in the "payment.method" model
    payment_method_viettelpay = env["payment.method"].search([("code", "=", "viettelpay")], limit=1)

    # Link the found payment method to the found payment provider
    if payment_method_viettelpay:
        payment_viettelpay.write({
            "payment_method_ids": [(6, 0, [payment_method_viettelpay.id])],
        })

def uninstall_hook(env):
    """
    Uninstallation hook to reset the ViettelPay payment provider.
    """
    # Reset the payment provider for "viettelpay"
    reset_payment_provider(env, "viettelpay")
