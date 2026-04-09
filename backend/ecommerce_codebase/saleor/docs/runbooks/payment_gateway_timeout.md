# Runbook: Payment Gateway Timeout

## Severity: P1

## Symptoms
- HTTP 504 errors on checkout completion
- Payment gateway response time > 30 seconds
- Spike in `payment_gateway_timeout_total` metric
- Customers reporting "Error processing payment" but getting charged

## Impact
- Customers may be charged without an order being created
- Lost revenue from abandoned checkouts
- Customer support ticket volume increases

## Triage Steps

### Step 1: Confirm the issue
```bash
# Check error rate
grep "Gateway timeout" /var/log/saleor/payment.log | wc -l

# Check gateway response times
grep "gateway_response_time" /var/log/saleor/metrics.log | tail -20
```

### Step 2: Check gateway provider status
- **Stripe**: https://status.stripe.com
- **Adyen**: https://status.adyen.com
- **PayPal**: https://www.paypal-status.com

### Step 3: Immediate mitigation
1. **DO NOT** increase the timeout beyond 30 seconds (this masks the problem)
2. If the primary gateway is down, switch to backup gateway:
   ```python
   # In Django admin or via env var:
   DEFAULT_PAYMENT_GATEWAY = "saleor.payment.gateways.backup_gateway"
   ```
3. If no backup gateway, enable "pay later" option or put checkout in maintenance mode

### Step 4: Reconcile orphaned payments
After the gateway recovers, reconcile payments that were charged but didn't create orders:

```python
from saleor.payment.models import Payment
from saleor.order.models import Order

# Find payments with no associated order
orphaned = Payment.objects.filter(
    charge_status="fully-charged",
    order__isnull=True,
    checkout__isnull=False,
)

for payment in orphaned:
    print(f"Payment {payment.pk}: {payment.total} {payment.currency}")
    print(f"  Gateway: {payment.gateway}, Token: {payment.token}")
    print(f"  Checkout: {payment.checkout_id}")
    # Manually create order or issue refund
```

### Step 5: Customer communication
- Send apology email to affected customers
- If charged without order: prioritize refund within 24h
- Update status page with incident details

## Post-Incident
- Review gateway SLA compliance
- Consider adding circuit breaker pattern
- Review if timeout threshold should be adjusted
- Add alerting on `payment_gateway_response_time > 10s`

## Escalation
- If >5% of payments are timing out → P1 page SRE oncall
- If customers are being double-charged → P1 + notify finance
- If gateway outage > 1 hour → activate backup gateway
