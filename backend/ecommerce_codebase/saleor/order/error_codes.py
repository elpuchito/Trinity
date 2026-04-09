"""
Saleor Order Error Codes.

These error codes are returned in GraphQL mutation responses and logged
in application error handlers. Use these codes to identify the specific
failure mode in incident reports.
"""

from enum import Enum


class OrderErrorCode(str, Enum):
    BILLING_ADDRESS_NOT_SET = "billing_address_not_set"
    CANNOT_CANCEL_FULFILLMENT = "cannot_cancel_fulfillment"
    CANNOT_CANCEL_ORDER = "cannot_cancel_order"
    CANNOT_DELETE = "cannot_delete"
    CANNOT_DISCOUNT = "cannot_discount"
    CANNOT_REFUND = "cannot_refund"
    CAPTURE_INACTIVE_PAYMENT = "capture_inactive_payment"
    CHANNEL_INACTIVE = "channel_inactive"
    DUPLICATED_INPUT_ITEM = "duplicated_input_item"
    FULFILL_ORDER_LINE = "fulfill_order_line"
    GRAPHQL_ERROR = "graphql_error"
    INSUFFICIENT_STOCK = "insufficient_stock"
    INVALID = "invalid"
    INVALID_QUANTITY = "invalid_quantity"
    NOT_AVAILABLE_IN_CHANNEL = "not_available_in_channel"
    NOT_EDITABLE = "not_editable"
    NOT_FOUND = "not_found"
    ORDER_NO_SHIPPING_ADDRESS = "order_no_shipping_address"
    PAYMENT_ERROR = "payment_error"
    PAYMENT_MISSING = "payment_missing"
    PRODUCT_NOT_PUBLISHED = "product_not_published"
    PRODUCT_UNAVAILABLE_FOR_PURCHASE = "product_unavailable_for_purchase"
    REQUIRED = "required"
    SHIPPING_METHOD_NOT_APPLICABLE = "shipping_method_not_applicable"
    SHIPPING_METHOD_REQUIRED = "shipping_method_required"
    TAX_ERROR = "tax_error"
    UNIQUE = "unique"
    VOID_INACTIVE_PAYMENT = "void_inactive_payment"
    ZERO_QUANTITY = "zero_quantity"
    MISSING_TRANSACTION_ACTION_REQUEST_WEBHOOK = "missing_transaction_action_request_webhook"
