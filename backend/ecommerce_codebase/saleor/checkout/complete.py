"""
Saleor Checkout Completion — The most critical code path.

This module handles the full checkout → order conversion flow.
It is the #1 source of production incidents in the Saleor platform.

ALERT: Any changes to this module require thorough testing with:
- Happy path (normal checkout completion)
- Payment gateway timeout scenarios
- Concurrent completion attempts
- Empty checkout edge case
- Missing pricing edge case
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """Base exception for checkout failures."""
    def __init__(self, message, code=None, checkout_id=None):
        self.code = code
        self.checkout_id = checkout_id
        super().__init__(message)


def complete_checkout(checkout, payment_data=None, user=None, app=None):
    """
    Complete a checkout and create an order.

    This is the most critical function in the entire e-commerce stack.
    
    FLOW:
    1. Validate checkout state (lines, pricing, addresses)
    2. Lock checkout (prevent concurrent completions)
    3. Process payment (authorize or capture)
    4. Create order from checkout
    5. Send confirmation notifications
    6. Delete the checkout
    
    COMMON FAILURE MODES:
    
    1. HTTP 500: "TypeError: Cannot read property 'total_gross_amount' of undefined"
       Root cause: The checkout pricing plugin (TaxJar/Avalara) returned an error
       or timed out, leaving total_gross_amount as None. When the frontend tries
       to display the total after submission, it crashes.
       Fix: Re-trigger pricing calculation before completing checkout.
       
    2. HTTP 500: "IntegrityError: duplicate key value violates unique constraint"
       Root cause: Race condition — two concurrent POST requests to checkoutComplete.
       The first request creates the order, the second fails because the checkout
       already has completing_started_at set.
       Fix: This is actually the correct behavior (the lock prevented a double-order).
       Frontend should handle 500 gracefully and poll for order status.
       
    3. HTTP 504: "Gateway Timeout"
       Root cause: The payment gateway (Stripe/Adyen) is slow to respond.
       The proxy times out at 30s, but the payment may still complete.
       Fix: Check payment gateway dashboard. If payment succeeded, manually
       create the order. If not, retry.
       
    4. HTTP 400: "INSUFFICIENT_STOCK"
       Root cause: Stock decreased between cart addition and checkout completion.
       This is common during flash sales or high-traffic events.
       Fix: Show user-friendly error. Suggest alternative variants.

    Args:
        checkout: The Checkout to complete.
        payment_data: Dictionary with payment gateway response data.
        user: The authenticated user.
        app: Optional App reference.

    Returns:
        Order: The newly created order.

    Raises:
        CheckoutError: If the checkout cannot be completed.
    """
    logger.info("Starting checkout completion for %s", checkout.token)
    
    # Step 1: Validate
    _validate_checkout(checkout)
    
    # Step 2: Lock
    checkout.completing_started_at = datetime.now(timezone.utc)
    checkout.save(update_fields=["completing_started_at"])
    
    try:
        # Step 3: Process payment
        payment = _process_checkout_payment(checkout, payment_data)
        
        # Step 4: Create order
        from saleor.order.actions import create_order_from_checkout
        order = create_order_from_checkout(checkout, user, app)
        
        # Step 5: Send notifications
        _send_order_confirmation(order)
        
        # Step 6: Cleanup
        checkout.delete()
        
        logger.info(
            "Checkout %s completed → Order %s (total: %s %s)",
            checkout.token, order.pk, order.total_gross_amount, order.currency,
        )
        return order
        
    except Exception as e:
        # Unlock checkout on failure so customer can retry
        checkout.completing_started_at = None
        checkout.save(update_fields=["completing_started_at"])
        logger.error("Checkout completion failed for %s: %s", checkout.token, e)
        raise


def _validate_checkout(checkout):
    """Validate that the checkout is in a completable state.
    
    Common validation failures:
    - Empty checkout (no lines) → EMPTY_CHECKOUT
    - No email set (anonymous checkout without email) → EMAIL_NOT_SET
    - Pricing not calculated (total is None) → CHECKOUT_NOT_FULLY_PAID
    - Shipping required but no address → SHIPPING_ADDRESS_NOT_SET
    - Shipping required but no method selected → SHIPPING_METHOD_NOT_SET
    """
    if not checkout.lines.exists():
        raise CheckoutError(
            "Cannot complete empty checkout",
            code="EMPTY_CHECKOUT",
            checkout_id=str(checkout.token),
        )
    
    if checkout.total_gross_amount is None:
        raise CheckoutError(
            "Checkout pricing has not been calculated. "
            "The pricing service may be unavailable.",
            code="CHECKOUT_NOT_FULLY_PAID",
            checkout_id=str(checkout.token),
        )
    
    if not checkout.email and not checkout.user:
        raise CheckoutError(
            "Email is required for checkout",
            code="EMAIL_NOT_SET",
            checkout_id=str(checkout.token),
        )
    
    if checkout.is_shipping_required:
        if not checkout.shipping_address:
            raise CheckoutError(
                "Shipping address is required",
                code="SHIPPING_ADDRESS_NOT_SET",
                checkout_id=str(checkout.token),
            )
        if not checkout.shipping_method:
            raise CheckoutError(
                "Shipping method is required",
                code="SHIPPING_METHOD_NOT_SET",
                checkout_id=str(checkout.token),
            )


def _process_checkout_payment(checkout, payment_data=None):
    """Process payment for checkout completion.
    
    INCIDENT PATTERN: Payment gateway timeout.
    
    The Stripe/Adyen gateway has a 30-second timeout configured in the plugin.
    If the gateway doesn't respond within 30s, a PaymentError is raised.
    However, the payment may still be processing on the gateway side.
    
    NEVER automatically retry a payment that timed out — this can cause
    double-charges. Instead:
    1. Check the gateway dashboard for the transaction
    2. If it went through, manually create the order
    3. If it failed, allow the customer to retry
    """
    pass  # Payment processing implementation


def _send_order_confirmation(order):
    """Send order confirmation email and notifications.
    
    Uses Celery for async delivery. If Celery is down, notifications
    are queued in Redis and retried on next Celery restart.
    """
    pass  # Notification implementation
