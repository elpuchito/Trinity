"""
Saleor Order Models — Synthetic representative code.

This module defines the core Order and OrderLine models for the Saleor e-commerce platform.
Orders represent completed purchases and track fulfillment, payment, and shipping state.
"""

from django.db import models
from django.conf import settings
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    DRAFT = "draft"
    UNCONFIRMED = "unconfirmed"
    UNFULFILLED = "unfulfilled"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    FULFILLED = "fulfilled"
    PARTIALLY_RETURNED = "partially_returned"
    RETURNED = "returned"
    CANCELED = "canceled"
    EXPIRED = "expired"


class OrderEvents(str, Enum):
    """Events that can occur during an order's lifecycle."""
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PAYMENT_CAPTURED = "payment_captured"
    PAYMENT_REFUNDED = "payment_refunded"
    FULFILLMENT_CANCELED = "fulfillment_canceled"
    ORDER_FULLY_PAID = "order_fully_paid"
    TRACKING_UPDATED = "tracking_updated"
    NOTE_ADDED = "note_added"
    EMAIL_SENT = "email_sent"


class Order(models.Model):
    """
    Represents a customer order in the e-commerce system.

    An Order is created when a Checkout is completed. It tracks:
    - Line items (OrderLine)
    - Payment status and transactions
    - Fulfillment and shipping status
    - Discounts and vouchers applied

    Common error patterns:
    - total_gross_amount can be None if pricing calculation fails during checkout completion
    - shipping_address may be null for digital-only orders
    - Concurrent modifications to order status can cause race conditions (use select_for_update)
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=32,
        default=OrderStatus.UNFULFILLED,
        choices=[(s.value, s.name) for s in OrderStatus],
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="orders",
        on_delete=models.SET_NULL,
    )
    tracking_client_id = models.CharField(max_length=36, blank=True, default="")
    billing_address = models.ForeignKey(
        "account.Address", related_name="+", editable=False,
        null=True, on_delete=models.SET_NULL,
    )
    shipping_address = models.ForeignKey(
        "account.Address", related_name="+", editable=False,
        null=True, on_delete=models.SET_NULL,
    )
    channel = models.ForeignKey(
        "channel.Channel", related_name="orders", on_delete=models.PROTECT,
    )
    shipping_method_name = models.CharField(max_length=255, null=True, default=None)
    total_net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    voucher = models.ForeignKey(
        "discount.Voucher", blank=True, null=True, related_name="+",
        on_delete=models.SET_NULL,
    )
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    weight = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))

    class Meta:
        ordering = ("-created_at",)
        permissions = (("manage_orders", "Manage orders."),)

    def __str__(self):
        return f"Order #{self.pk}"

    @property
    def is_fully_paid(self):
        """Check if the order total has been fully captured in payments."""
        total_paid = sum(
            payment.captured_amount
            for payment in self.payments.filter(is_active=True)
        )
        return total_paid >= self.total_gross_amount

    @property
    def total_balance(self):
        """Calculate the balance: total_charged - total_gross_amount.
        
        WARNING: This can raise AttributeError if total_gross_amount is None,
        which happens when the checkout pricing calculation fails.
        The caller should handle this case explicitly.
        """
        return self.total_charged_amount - self.total_gross_amount

    def can_cancel(self):
        """Determine if this order can be canceled.
        
        Returns False if any fulfillment has been shipped.
        Raises ValueError if order is in DRAFT status (drafts should be deleted, not canceled).
        """
        if self.status == OrderStatus.DRAFT:
            raise ValueError("Draft orders cannot be canceled. Delete the draft instead.")
        if self.status == OrderStatus.CANCELED:
            return False
        return not self.fulfillments.exclude(
            status=FulfillmentStatus.CANCELED
        ).exists()


class OrderLine(models.Model):
    """
    A single line item in an Order.
    
    Each OrderLine corresponds to one product variant purchased.
    
    Known issues:
    - quantity can be 0 if a partial fulfillment reduces it, causing division-by-zero
      in per-unit price calculations
    - unit_price_gross_amount can drift from the original product price if the product
      price is updated after the order is placed. This is by design (price lock).
    """
    order = models.ForeignKey(
        Order, related_name="lines", editable=False, on_delete=models.CASCADE,
    )
    variant = models.ForeignKey(
        "product.ProductVariant", related_name="+", on_delete=models.SET_NULL,
        blank=True, null=True,
    )
    product_name = models.CharField(max_length=386)
    variant_name = models.CharField(max_length=255, default="")
    product_sku = models.CharField(max_length=255, null=True)
    quantity = models.IntegerField(default=1)
    unit_price_net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price_gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_price_net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_price_gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    is_shipping_required = models.BooleanField(default=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"{self.product_name} ({self.variant_name}) x{self.quantity}"

    @property
    def unit_price(self):
        """Return the gross unit price. Can be Decimal('0') if not set."""
        return self.unit_price_gross_amount or Decimal("0")
"""
