# Common Errors & Troubleshooting Guide

## Error Index

### HTTP 500 Errors

#### 1. `TypeError: unsupported operand type(s) for -: 'NoneType' and 'Decimal'`

**Affected modules:** `saleor/checkout/complete.py`, `saleor/order/actions.py`

**Root cause:** The pricing plugin (TaxJar/Avalara) failed to calculate taxes, leaving `checkout.total_gross_amount` as `None`. When the system tries to do arithmetic on this value, it crashes.

**Symptoms:**
- Checkout completion fails for ALL customers
- Error appears in Sentry with high frequency
- Tax calculation requests timing out in the logs

**Resolution:**
1. Check if the tax provider (TaxJar/Avalara) is accessible
2. Look for timeout errors in the `saleor.plugins.tax` logs
3. If the provider is down, temporarily disable auto-tax calculation
4. Trigger a price recalculation for affected checkouts:
   ```python
   for checkout in Checkout.objects.filter(total_gross_amount__isnull=True):
       recalculate_checkout_prices(checkout)
   ```

---

#### 2. `IntegrityError: duplicate key value violates unique constraint "order_order_pkey"`

**Affected modules:** `saleor/order/actions.py`

**Root cause:** Race condition during checkout completion. Two concurrent requests try to create an order from the same checkout. The `completing_started_at` lock field should prevent this, but there's a small window between the check and the lock.

**Symptoms:**
- Sporadic 500s on checkout completion
- Usually happens during high traffic or when customers double-click "Place Order"

**Resolution:**
1. This is usually harmless — only one order was created
2. Check that only one order exists for the checkout
3. If the customer reports a double charge, check the payment gateway dashboard

---

### HTTP 504 Errors

#### 3. `Gateway Timeout` on `/graphql` endpoint

**Affected modules:** `saleor/payment/gateway.py`

**Root cause:** Payment gateway (Stripe/Adyen) is slow to respond, exceeding the 30-second proxy timeout.

**Symptoms:**
- Checkout completion returns 504 to the customer
- Payment may have been charged despite the timeout
- `PAYMENT_GATEWAY_TIMEOUT` appears in error logs

**Resolution:**
1. **DO NOT** automatically retry the payment
2. Check the payment gateway dashboard for the transaction
3. If payment was charged: manually create the order using Django admin
4. If payment was not charged: customer can safely retry

---

### HTTP 400 Errors

#### 4. `INSUFFICIENT_STOCK` during checkout

**Affected modules:** `saleor/order/actions.py`, `saleor/product/models.py`

**Root cause:** Stock quantity decreased between cart creation and checkout completion. Common during flash sales.

**Symptoms:**
- Customer gets "Insufficient stock" error at the last step
- Multiple concurrent orders depleting the same stock

**Resolution:**
1. This is expected behavior — not a bug
2. Check stock levels: `Stock.objects.filter(product_variant_id=XXX)`
3. If stock shows available but error persists, check `quantity_allocated`
4. Run stock reconciliation: `python manage.py reconcile_stock`

---

#### 5. `CHECKOUT_NOT_FULLY_PAID` 

**Affected modules:** `saleor/checkout/complete.py`

**Root cause:** The checkout total is None because pricing was never calculated or the calculation failed.

**Symptoms:**
- Error appears after adding items to cart and trying to checkout
- Usually correlates with pricing plugin failures

**Resolution:**
1. Check pricing plugin health
2. Force recalculation: `POST /graphql` with `checkoutLinesUpdate` mutation
3. If persistent, check if the product's `ProductChannelListing` has a price set

---

### GraphQL Errors

#### 6. `PermissionDenied` on order mutations

**Affected modules:** `saleor/graphql/order/mutations.py`

**Root cause:** The API token used doesn't have the required permissions.

**Resolution:**
1. Check the app/user token permissions
2. Required permission for order management: `MANAGE_ORDERS`
3. Required permission for payment capture: `HANDLE_PAYMENTS`

---

#### 7. Slow GraphQL queries (>5s response time)

**Affected modules:** `saleor/graphql/`, database

**Root cause:** N+1 queries or missing database indexes.

**Common slow queries:**
- `products` query with many nested fields (variants, images, attributes)
- `orders` query without filters (scans entire table)
- `checkoutLines` with stock availability check (N+1 on Stock table)

**Resolution:**
1. Check `EXPLAIN ANALYZE` for the slow query
2. Add database indexes for commonly filtered fields
3. Use DataLoader for N+1 patterns
4. Set `GRAPHQL_QUERY_MAX_COMPLEXITY` to limit query depth

---

## Performance Monitoring

### Key Metrics
- `checkout_completion_time_seconds` — P99 should be < 10s
- `payment_gateway_response_time_seconds` — P99 should be < 5s
- `graphql_query_time_seconds` — P99 should be < 2s
- `celery_task_latency_seconds` — P99 should be < 30s
- `stock_sync_lag_seconds` — Should be < 300s (5 min)

### Health Check Endpoints
- `/health/` — Basic Django health check
- `/health/readiness/` — Full readiness (DB + Redis + Celery)
