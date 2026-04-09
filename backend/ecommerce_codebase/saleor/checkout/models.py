"""
Saleor Checkout Models — Synthetic representative code.

This module defines the Checkout and CheckoutLine models.
A Checkout is a transient shopping cart that gets converted into an Order
when the customer completes the purchase flow.
"""

from django.db import models
from django.conf import settings
from decimal import Decimal
from uuid import uuid4


class Checkout(models.Model):
    """
    Represents an active shopping session / cart.
    
    The Checkout is the central object during the purchase flow. It accumulates
    line items, shipping info, and payment details until the customer completes
    the purchase, at which point it is converted to an Order.
    
    CRITICAL ERROR PATTERNS:
    
    1. total_gross_amount = None
       This happens when the pricing plugin (e.g., TaxJar, Avalara) fails to respond.
       The checkout can be saved with None pricing, but attempting to complete it will
       crash with: TypeError: unsupported operand type(s) for -: 'NoneType' and 'Decimal'
       
    2. Stale checkout
       Checkouts older than 30 days are cleaned up by a cron job. If a customer returns
       to a stale link, they'll get a 404 on the checkout endpoint. This is expected
       behavior but generates many false-alarm incident reports.
       
    3. Concurrent modifications
       Multiple browser tabs modifying the same checkout can cause line item conflicts.
       The system uses last-write-wins, which can silently drop items.
       
    4. Channel mismatch
       If a checkout is created in channel A but the customer switches to channel B,
       product availability and pricing will be inconsistent. The system should
       validate channel consistency on completion.
    """
    token = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_change = models.DateTimeField(auto_now=True)
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True,
        related_name="checkouts", on_delete=models.CASCADE,
    )
    email = models.EmailField(blank=True, null=True)
    
    channel = models.ForeignKey(
        "channel.Channel", related_name="checkouts", on_delete=models.PROTECT,
    )
    
    billing_address = models.ForeignKey(
        "account.Address", related_name="+", null=True,
        on_delete=models.SET_NULL,
    )
    shipping_address = models.ForeignKey(
        "account.Address", related_name="+", null=True,
        on_delete=models.SET_NULL,
    )
    shipping_method = models.ForeignKey(
        "shipping.ShippingMethod", blank=True, null=True,
        related_name="checkouts", on_delete=models.SET_NULL,
    )
    
    # Pricing — can be None if pricing service fails
    total_net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), null=True,
    )
    total_gross_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), null=True,
    )
    subtotal_net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), null=True,
    )
    subtotal_gross_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), null=True,
    )
    currency = models.CharField(max_length=3, default="USD")
    
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
    )
    discount_name = models.CharField(max_length=255, blank=True, null=True)
    voucher_code = models.CharField(max_length=255, blank=True, null=True)
    
    note = models.TextField(blank=True, default="")
    
    # Completion tracking
    completing_started_at = models.DateTimeField(null=True, blank=True)
    
    @property
    def is_shipping_required(self):
        """Check if any line in the checkout requires shipping."""
        return self.lines.filter(
            variant__product__product_type__is_shipping_required=True
        ).exists()
    
    @property
    def quantity(self):
        """Total number of items in checkout."""
        return sum(line.quantity for line in self.lines.all())
    
    def get_total_price(self):
        """Get the total price of the checkout.
        
        WARNING: Returns None if pricing has not been calculated.
        Callers must handle the None case.
        """
        if self.total_gross_amount is None:
            return None
        return self.total_gross_amount


class CheckoutLine(models.Model):
    """
    A single line item in a Checkout.
    
    Known issue: If the variant is deleted while a checkout containing it 
    is still active, the line becomes orphaned and causes NullPointerExceptions
    when iterating checkout lines for pricing calculation.
    """
    id = models.AutoField(primary_key=True)
    checkout = models.ForeignKey(
        Checkout, related_name="lines", on_delete=models.CASCADE,
    )
    variant = models.ForeignKey(
        "product.ProductVariant", related_name="+",
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("checkout", "variant")
        ordering = ("created_at", "id")

    def __str__(self):
        return f"CheckoutLine: {self.variant} x{self.quantity}"
