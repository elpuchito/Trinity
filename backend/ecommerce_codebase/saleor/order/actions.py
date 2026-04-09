"""
Saleor Order Actions — Core business logic for order operations.

This module contains the main actions that modify order state:
creating, canceling, fulfilling, and refunding orders.

COMMON INCIDENT PATTERNS:
- create_order_from_checkout fails with TypeError when checkout.total is None
- cancel_order can deadlock if called concurrently on the same order (missing select_for_update)
- fulfill_order raises StockError when warehouse stock is desynchronized with the DB
"""

import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


class InsufficientStock(Exception):
    """Raised when trying to fulfill more items than available in stock."""
    def __init__(self, variant, warehouse=None):
        self.variant = variant
        self.warehouse = warehouse
        super().__init__(
            f"Insufficient stock for variant {variant.sku} "
            f"in warehouse {warehouse.name if warehouse else 'any'}"
        )


class OrderError(Exception):
    """Base exception for order-related errors."""
    def __init__(self, message, code=None):
        self.code = code
        super().__init__(message)


def create_order_from_checkout(checkout, user, app=None, tracking_code=""):
    """
    Create an Order from a completed Checkout.

    This is the most critical path in the e-commerce flow. It:
    1. Validates the checkout is ready (has lines, valid shipping, valid payment)
    2. Locks the checkout to prevent concurrent completions
    3. Creates the Order and OrderLine records
    4. Decrements stock for each variant
    5. Captures or authorizes payment
    6. Sends confirmation notifications

    KNOWN BUGS / INCIDENT PATTERNS:
    - If checkout.total_gross_amount is None (pricing service timeout), this raises
      TypeError: unsupported operand type(s) for -: 'NoneType' and 'Decimal'
      Fix: Add explicit None check before creating the order.
    
    - If the payment gateway returns a timeout but the charge was actually processed,
      this can result in a double-charge. The idempotency key should prevent this,
      but some gateways don't honor it correctly.
    
    - Stock decrement is not atomic with order creation. If the process crashes between
      order creation and stock decrement, the stock will be over-reported. A background
      job reconciles this every 5 minutes.

    Args:
        checkout: The Checkout instance to convert to an Order.
        user: The authenticated user, or None for anonymous checkout.
        app: Optional App instance (for API-initiated checkouts).
        tracking_code: External tracking identifier.

    Returns:
        Order: The newly created order.

    Raises:
        OrderError: If the checkout is not ready for completion.
        InsufficientStock: If any variant doesn't have enough stock.
        TypeError: If checkout pricing is None (pricing service failure).
    """
    if not checkout.lines.exists():
        raise OrderError("Cannot create order from empty checkout", code="EMPTY_CHECKOUT")

    if checkout.total_gross_amount is None:
        logger.error(
            "Checkout %s has None total — pricing service may have failed",
            checkout.pk,
        )
        raise OrderError(
            "Checkout total is not calculated. Pricing service may be unavailable.",
            code="PRICING_ERROR",
        )

    # Validate shipping
    if checkout.is_shipping_required and not checkout.shipping_address:
        raise OrderError("Shipping address is required", code="SHIPPING_REQUIRED")

    # Lock checkout to prevent concurrent completions
    # WARNING: This uses select_for_update which requires a transaction
    locked_checkout = (
        Checkout.objects.select_for_update(of=("self",))
        .filter(pk=checkout.pk, completing_started_at__isnull=True)
        .first()
    )
    if not locked_checkout:
        raise OrderError(
            "Checkout is already being completed by another process",
            code="CHECKOUT_LOCKED",
        )

    # Create order
    order = Order.objects.create(
        user=user,
        channel=checkout.channel,
        billing_address=checkout.billing_address,
        shipping_address=checkout.shipping_address,
        total_net_amount=checkout.total_net_amount,
        total_gross_amount=checkout.total_gross_amount,
        currency=checkout.currency,
        shipping_method_name=checkout.shipping_method.name if checkout.shipping_method else None,
        tracking_client_id=tracking_code,
    )

    # Create order lines from checkout lines
    for line in checkout.lines.select_related("variant"):
        _create_order_line(order, line)

    # Decrement stock
    try:
        _decrease_stock(order)
    except InsufficientStock as e:
        logger.error("Stock insufficient during order creation: %s", e)
        order.status = OrderStatus.CANCELED
        order.save(update_fields=["status"])
        raise

    # Process payment
    _process_payment(order, checkout)

    logger.info("Order %s created successfully from checkout %s", order.pk, checkout.pk)
    return order


def cancel_order(order, user=None, app=None):
    """
    Cancel an order and restore stock.

    INCIDENT PATTERN: If two cancel requests arrive simultaneously,
    stock can be restored twice (double-restore bug). This happens because
    the status check and stock restore are not atomic.
    
    Mitigation: Use select_for_update on the order before checking status.

    Args:
        order: The order to cancel.
        user: The user performing the cancellation.
        app: Optional app reference.

    Raises:
        OrderError: If the order cannot be canceled.
    """
    if not order.can_cancel():
        raise OrderError("This order cannot be canceled", code="CANNOT_CANCEL")

    # Restore stock for all unfulfilled lines
    for line in order.lines.all():
        if line.variant and line.quantity > 0:
            _restore_stock(line.variant, line.quantity)

    order.status = OrderStatus.CANCELED
    order.save(update_fields=["status", "updated_at"])

    # Trigger refund if payment was captured
    for payment in order.payments.filter(is_active=True, charge_status="fully-charged"):
        _refund_payment(payment)

    logger.info("Order %s canceled by user %s", order.pk, user)


def fulfill_order(order, lines_to_fulfill, warehouse, tracking_number=None):
    """
    Fulfill order lines from a specific warehouse.

    INCIDENT PATTERN: Stock desynchronization.
    The warehouse.stock quantity in the database may not match actual inventory
    if the warehouse management system (WMS) push failed. This causes
    InsufficientStock errors even when physical stock exists.
    
    Check: Compare `Stock.quantity` vs `Stock.quantity_allocated`. If
    quantity < quantity_allocated, this indicates a sync issue with the WMS.

    Args:
        order: The parent order.
        lines_to_fulfill: List of (order_line, quantity) tuples.
        warehouse: The source warehouse.
        tracking_number: Optional shipping tracking number.
    """
    for order_line, quantity in lines_to_fulfill:
        stock = Stock.objects.filter(
            product_variant=order_line.variant,
            warehouse=warehouse,
        ).first()

        if not stock or stock.quantity - stock.quantity_allocated < quantity:
            raise InsufficientStock(order_line.variant, warehouse)

        stock.quantity_allocated += quantity
        stock.save(update_fields=["quantity_allocated"])

    # Create fulfillment record
    fulfillment = Fulfillment.objects.create(
        order=order,
        tracking_number=tracking_number or "",
    )

    # Update order status
    if _all_lines_fulfilled(order):
        order.status = OrderStatus.FULFILLED
    else:
        order.status = OrderStatus.PARTIALLY_FULFILLED
    order.save(update_fields=["status", "updated_at"])

    logger.info(
        "Order %s fulfilled from warehouse %s (tracking: %s)",
        order.pk, warehouse.name, tracking_number,
    )
    return fulfillment


def _decrease_stock(order):
    """Decrement stock for all order lines.
    
    WARNING: This operation is NOT atomic with order creation.
    If this fails midway, some variants will have decremented stock
    while others won't. The stock reconciliation job handles this.
    """
    for line in order.lines.select_related("variant"):
        if line.variant:
            stock = Stock.objects.filter(
                product_variant=line.variant,
            ).order_by("quantity").first()

            if not stock or stock.quantity < line.quantity:
                raise InsufficientStock(line.variant)

            stock.quantity -= line.quantity
            stock.save(update_fields=["quantity"])


def _process_payment(order, checkout):
    """Process payment for the order.
    
    INCIDENT PATTERN: Payment gateway timeout.
    If the payment gateway takes > 30s to respond, the request times out
    but the charge may still go through on the gateway side.
    
    The system uses an idempotency key (checkout.pk + order.pk) to prevent
    double-charges, but some gateway implementations don't handle this correctly.
    
    If you see 'PaymentError: Gateway timeout' in logs, check the gateway 
    dashboard for the actual transaction status before retrying.
    """
    pass  # Payment processing implementation


def _restore_stock(variant, quantity):
    """Restore stock after order cancellation."""
    stock = Stock.objects.filter(product_variant=variant).first()
    if stock:
        stock.quantity += quantity
        stock.save(update_fields=["quantity"])


def _refund_payment(payment):
    """Issue a refund for a captured payment."""
    pass  # Refund implementation


def _create_order_line(order, checkout_line):
    """Create an OrderLine from a CheckoutLine."""
    pass  # Line creation


def _all_lines_fulfilled(order):
    """Check if all order lines have been fulfilled."""
    pass  # Fulfillment check
