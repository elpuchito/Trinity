"""
Saleor Payment Models — Synthetic representative code.

Handles payment transactions, gateway interactions, and refund tracking.
"""

from django.db import models
from decimal import Decimal
from enum import Enum
from uuid import uuid4


class ChargeStatus(str, Enum):
    NOT_CHARGED = "not-charged"
    PENDING = "pending"
    PARTIALLY_CHARGED = "partially-charged"
    FULLY_CHARGED = "fully-charged"
    PARTIALLY_REFUNDED = "partially-refunded"
    FULLY_REFUNDED = "fully-refunded"
    REFUSED = "refused"
    CANCELLED = "cancelled"


class TransactionKind(str, Enum):
    AUTH = "auth"
    CAPTURE = "capture"
    VOID = "void"
    REFUND = "refund"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    PENDING = "pending"


class Payment(models.Model):
    """
    Represents a payment associated with an order or checkout.
    
    CRITICAL INCIDENT PATTERNS:
    
    1. Ghost payments: Payment.is_active=True but no Transaction records exist.
       This happens when the payment creation succeeds but the gateway call fails
       before creating a Transaction. The payment appears "active" but has no
       actual gateway reference. These need manual cleanup.
       
    2. Double charges: Two Payment records with charge_status=FULLY_CHARGED 
       for the same order. This is caused by race conditions in the checkout
       completion flow when the customer double-clicks "Place Order".
       Query: Payment.objects.filter(order=order, charge_status='fully-charged').count() > 1
       
    3. Stuck PENDING: Payment stays in charge_status=PENDING indefinitely.
       The gateway webhook that should update the status was either lost or
       the webhook endpoint returned an error. Check the gateway dashboard
       and manually update if needed.
       
    4. Currency mismatch: Payment.currency != Order.currency, which causes
       display issues and incorrect balance calculations. This is a data
       integrity issue from legacy migrations.
    """
    gateway = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    
    # Foreign keys
    checkout = models.ForeignKey(
        "checkout.Checkout", null=True, blank=True,
        related_name="payments", on_delete=models.SET_NULL,
    )
    order = models.ForeignKey(
        "order.Order", null=True, blank=True,
        related_name="payments", on_delete=models.PROTECT,
    )
    
    # Amounts
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    captured_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    charge_status = models.CharField(
        max_length=20,
        default=ChargeStatus.NOT_CHARGED,
        choices=[(s.value, s.name) for s in ChargeStatus],
    )
    
    # Gateway reference
    token = models.CharField(max_length=512, blank=True, default="")
    psp_reference = models.CharField(max_length=512, blank=True, default="")
    
    # Metadata
    billing_email = models.EmailField(blank=True, default="")
    billing_first_name = models.CharField(max_length=256, blank=True, default="")
    billing_last_name = models.CharField(max_length=256, blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    
    extra_data = models.TextField(blank=True, default="")
    return_url = models.URLField(blank=True, null=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"Payment #{self.pk} ({self.gateway}) [{self.charge_status}]"

    @property
    def is_authorized(self):
        return self.transactions.filter(kind=TransactionKind.AUTH, is_success=True).exists()

    def can_capture(self):
        """Check if this payment can be captured.
        
        WARNING: Returns False for inactive payments, but does NOT check
        if the gateway authorization has expired. Most gateways expire
        authorizations after 7 days. If you try to capture an expired
        auth, the gateway will return EXPIRED_AUTHORIZATION error.
        """
        return self.is_active and self.is_authorized and self.charge_status == ChargeStatus.NOT_CHARGED

    def can_refund(self):
        return (
            self.is_active
            and self.charge_status in (ChargeStatus.FULLY_CHARGED, ChargeStatus.PARTIALLY_REFUNDED)
        )


class Transaction(models.Model):
    """
    Individual payment transaction (auth, capture, refund, void).
    
    Each gateway operation creates a Transaction record. Transaction.is_success
    indicates whether the gateway confirmed the operation.
    
    INCIDENT PATTERN: Transaction with is_success=True but the gateway
    actually rejected the operation. This happens when the gateway returns
    a success response but with an error in the response body that our
    parser doesn't detect. Check Transaction.gateway_response JSON for
    actual status codes.
    """
    payment = models.ForeignKey(
        Payment, related_name="transactions", on_delete=models.PROTECT,
    )
    token = models.CharField(max_length=512, blank=True, default="")
    kind = models.CharField(
        max_length=25,
        choices=[(k.value, k.name) for k in TransactionKind],
    )
    is_success = models.BooleanField(default=False)
    action_required = models.BooleanField(default=False)
    
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    
    error = models.CharField(max_length=256, null=True)
    gateway_response = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"Transaction {self.kind} {'✓' if self.is_success else '✗'} {self.amount} {self.currency}"
