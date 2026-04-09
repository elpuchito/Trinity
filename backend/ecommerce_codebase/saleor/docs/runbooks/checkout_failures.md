# Runbook: Checkout Failures

## Severity: P1 (if affecting all users) / P2 (if affecting subset)

## Symptoms
- Customers unable to complete checkout
- HTTP 500 on `checkoutComplete` GraphQL mutation
- Spike in `checkout_completion_error_total` metric

## Triage Steps

### Step 1: Identify the error type
Check Sentry or application logs for the specific error:
```bash
grep "checkoutComplete" /var/log/saleor/error.log | tail -20
```

### Step 2: Classify the failure
| Error | Likely Cause | Go to Step |
|---|---|---|
| `TypeError: NoneType` | Pricing service failure | Step 3 |
| `InsufficientStock` | Stock depleted | Step 4 |
| `PaymentError` | Gateway issue | Step 5 |
| `IntegrityError` | Race condition | Step 6 |

### Step 3: Pricing Service Failure
1. Check TaxJar/Avalara status: `curl -s https://status.taxjar.com/api/v2/status.json`
2. Check pricing plugin logs: `grep "tax" /var/log/saleor/app.log | tail -50`
3. If provider is down:
   - Disable auto-tax: Set `TAX_CALCULATION_STRATEGY=flat` in env
   - Restart workers: `supervisorctl restart saleor-worker`
4. After fix, recalculate affected checkouts:
   ```python
   from saleor.checkout.utils import recalculate_checkout_prices
   nulled = Checkout.objects.filter(total_gross_amount__isnull=True)
   for c in nulled:
       recalculate_checkout_prices(c)
   ```

### Step 4: Stock Depletion
1. Check stock levels: `SELECT sku, quantity, quantity_allocated FROM stock JOIN variant`
2. If legitimate (sold out): No action needed, error is expected
3. If stock sync issue: Run `python manage.py reconcile_stock`
4. Check WMS webhook logs for failed deliveries

### Step 5: Payment Gateway Issue
1. **DO NOT RETRY** — check gateway dashboard first
2. Stripe status: https://status.stripe.com
3. Adyen status: https://status.adyen.com
4. Check gateway logs: `grep "gateway" /var/log/saleor/payment.log`
5. If gateway is down: Enable backup gateway or put site in "maintenance mode"
6. For individual stuck payments: check `Payment.charge_status` and reconcile manually

### Step 6: Race Condition
1. This is usually self-resolving (customer can retry)
2. Verify only one order was created per checkout
3. If double-order exists: cancel the duplicate, process refund

## Escalation
- If affecting >10% of checkouts → escalate to P1
- If payment gateway outage → notify finance team
- If pricing service outage >30min → switch to flat tax mode
