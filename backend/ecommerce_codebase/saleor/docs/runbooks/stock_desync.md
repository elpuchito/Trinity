# Runbook: Stock Desynchronization

## Severity: P2 (P1 if causing checkout failures)

## Symptoms
- "Insufficient stock" errors when product shows as available
- Warehouse management system (WMS) shows different stock levels than Saleor
- `quantity_allocated > quantity` in Stock records (oversold situation)
- Customers able to order products that are actually out of stock

## Impact
- Customers receive "item unavailable" after placing order
- Manual order cancellation and refund required
- Revenue loss from oversold items and abandoned carts

## Triage Steps

### Step 1: Identify affected products
```sql
-- Find desynchronized stock records
SELECT 
    pv.sku,
    pv.name,
    w.name as warehouse,
    s.quantity,
    s.quantity_allocated,
    s.quantity - s.quantity_allocated as available
FROM warehouse_stock s
JOIN product_productvariant pv ON s.product_variant_id = pv.id
JOIN warehouse_warehouse w ON s.warehouse_id = w.id
WHERE s.quantity < s.quantity_allocated
ORDER BY (s.quantity - s.quantity_allocated) ASC;
```

### Step 2: Determine the cause
| Symptom | Likely Cause |
|---|---|
| quantity_allocated > quantity | Race condition during concurrent orders |
| WMS quantity ≠ Saleor quantity | WMS sync webhook failed |
| Stock = 0 but product shows available | Cached availability not refreshed |
| Negative stock | Missing stock lock during fulfillment |

### Step 3: Quick fix for desynchronized records
```python
from saleor.product.models import Stock

# Fix oversold items (set quantity_allocated = quantity)
oversold = Stock.objects.filter(quantity__lt=models.F('quantity_allocated'))
for stock in oversold:
    print(f"Fixing {stock.product_variant.sku}: qty={stock.quantity}, alloc={stock.quantity_allocated}")
    stock.quantity_allocated = stock.quantity
    stock.save(update_fields=["quantity_allocated"])
```

### Step 4: Full stock reconciliation
```bash
# Run the stock reconciliation management command
python manage.py reconcile_stock --dry-run  # Preview changes
python manage.py reconcile_stock            # Apply fixes
```

### Step 5: Investigate WMS sync
1. Check webhook delivery logs: `grep "stock_update" /var/log/saleor/webhooks.log`
2. Verify WMS API endpoint is reachable
3. Check if webhook signing secret is correct
4. Re-trigger sync for affected SKUs

## Post-Incident
- Add monitoring alert: `stock.quantity_allocated > stock.quantity`
- Consider adding DB constraint: `CHECK (quantity >= 0)`
- Review if `select_for_update` is used in all stock modification paths
- Schedule regular stock reconciliation (daily cron job)

## Escalation
- If >50 SKUs affected → P1
- If affecting high-value products → notify merchandising team
- If WMS integration fully broken → P1 + contact WMS vendor
