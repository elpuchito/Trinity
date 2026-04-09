"""
Saleor Payment Gateway — Plugin interface for payment providers.

This module defines the abstract gateway interface that all payment plugins
must implement (Stripe, Adyen, PayPal, etc.).

INCIDENT PATTERNS:

1. Gateway timeout (>30s response time):
   - Symptom: HTTP 504 on checkout completion
   - Root cause: Payment provider is slow or experiencing an outage
   - Impact: Customer sees error, but payment may have been charged
   - Mitigation: Check gateway dashboard, use idempotency keys
   
2. Invalid API key:
   - Symptom: All payments fail with "Authentication failed" 
   - Root cause: API key expired or was rotated without updating env vars
   - Impact: Complete payment outage
   - Mitigation: Rotate keys in settings, restart workers
   
3. Webhook signature verification failure:
   - Symptom: Payment status updates not reflected in Saleor
   - Root cause: Webhook signing secret doesn't match
   - Impact: Orders stuck in "pending payment" status
   - Mitigation: Update PAYMENT_WEBHOOK_SECRET env var
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GatewayResponse:
    """Response from payment gateway."""
    is_success: bool
    kind: str  # auth, capture, void, refund
    amount: Decimal
    currency: str
    transaction_id: str = ""
    error: Optional[str] = None
    raw_response: Optional[dict] = None
    action_required: bool = False
    action_required_data: Optional[dict] = None
    psp_reference: str = ""


@dataclass
class PaymentData:
    """Data passed to gateway for processing."""
    amount: Decimal
    currency: str
    token: str = ""
    customer_email: str = ""
    billing_address: Optional[dict] = None
    shipping_address: Optional[dict] = None
    order_id: str = ""
    payment_metadata: Optional[dict] = None


class PaymentGateway(ABC):
    """Abstract base class for payment gateway plugins.
    
    All payment gateways must implement these methods.
    Each method should:
    - Return a GatewayResponse with is_success=True on success
    - Return a GatewayResponse with is_success=False and error message on failure
    - NEVER raise exceptions — always catch and wrap in GatewayResponse
    
    Timeout handling:
    - Each gateway call has a 30-second timeout
    - If the gateway doesn't respond in 30s, return GatewayResponse(is_success=False, error="Gateway timeout")
    - The caller (checkout completion) will NOT automatically retry
    """

    @abstractmethod
    def authorize(self, payment_data: PaymentData) -> GatewayResponse:
        """Authorize a payment (hold funds without capturing)."""

    @abstractmethod
    def capture(self, payment_data: PaymentData, amount: Decimal) -> GatewayResponse:
        """Capture a previously authorized payment."""

    @abstractmethod
    def void(self, payment_data: PaymentData) -> GatewayResponse:
        """Void/cancel a previously authorized payment."""

    @abstractmethod
    def refund(self, payment_data: PaymentData, amount: Decimal) -> GatewayResponse:
        """Refund a previously captured payment."""

    @abstractmethod
    def process_payment(self, payment_data: PaymentData) -> GatewayResponse:
        """One-step: authorize + capture in a single call."""

    @abstractmethod
    def get_payment_config(self) -> dict:
        """Return configuration for the payment form on the frontend."""

    def process_webhook(self, request_data: dict, headers: dict) -> Optional[GatewayResponse]:
        """Process incoming webhook from the payment provider.
        
        IMPORTANT: Always verify the webhook signature before processing.
        Unverified webhooks could be spoofed to change payment status.
        """
        return None


class StripeGateway(PaymentGateway):
    """Stripe payment gateway implementation.
    
    Configuration env vars:
    - STRIPE_SECRET_KEY: API secret key
    - STRIPE_PUBLIC_KEY: Publishable key (for frontend)
    - STRIPE_WEBHOOK_SECRET: Webhook signing secret
    
    Common Stripe-specific errors:
    - card_declined: Customer's card was declined
    - expired_card: Card has expired
    - incorrect_cvc: CVC check failed
    - processing_error: Stripe internal error (retry after 5s)
    - rate_limit: Too many API requests (back off)
    """

    def authorize(self, payment_data: PaymentData) -> GatewayResponse:
        """Create a Stripe PaymentIntent with capture_method=manual."""
        try:
            # stripe.PaymentIntent.create(...)
            pass
        except Exception as e:
            logger.error("Stripe authorization failed: %s", e)
            return GatewayResponse(
                is_success=False,
                kind="auth",
                amount=payment_data.amount,
                currency=payment_data.currency,
                error=str(e),
            )

    def capture(self, payment_data: PaymentData, amount: Decimal) -> GatewayResponse:
        """Capture a Stripe PaymentIntent."""
        pass

    def void(self, payment_data: PaymentData) -> GatewayResponse:
        """Cancel a Stripe PaymentIntent."""
        pass

    def refund(self, payment_data: PaymentData, amount: Decimal) -> GatewayResponse:
        """Create a Stripe Refund."""
        pass

    def process_payment(self, payment_data: PaymentData) -> GatewayResponse:
        """Create and immediately capture a Stripe PaymentIntent."""
        pass

    def get_payment_config(self) -> dict:
        return {"api_key": "pk_test_..."}
