{
    # Tên module
    'name': 'ViettelPay',
    'version': '1.0',

    # Loại module
    'category': 'Accounting/Payment Providers',

    'sequence': 5,

    'summary': 'Viettel Payment',
    'description': '',

    'author': 'Bui Nhat Tuan',

    'depends': ['base', 'payment'],

    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    'installable': True,
    'auto_install': False,
    'application': True, 

    'data': [
        'data/payment_provider_data.xml',
        'data/payment_method_data.xml',
        'views/payment_viettel_view.xml',
        'views/payment_viettel_template.xml',
    ],

    'license': 'LGPL-3',
}
