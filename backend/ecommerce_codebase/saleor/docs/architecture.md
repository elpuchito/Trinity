# Saleor Architecture Overview

## System Architecture

Saleor is a headless, open-source e-commerce platform built with Python, Django, and GraphQL.

### Core Components

1. **GraphQL API** — The primary interface. All storefront and dashboard operations go through the GraphQL API.
2. **Django Backend** — Business logic, database models, and celery tasks.
3. **PostgreSQL** — Primary data store for orders, products, users, and payments.
4. **Redis** — Used for caching, Celery task queue, and session storage.
5. **Celery Workers** — Background task processing (email sending, webhook delivery, stock sync).
6. **Media Storage** — S3-compatible storage for product images and thumbnails.

### Request Flow

```
Client → Load Balancer → Gunicorn → Django → GraphQL → Resolvers → Models → PostgreSQL
                                                ↕
                                          Celery Workers → Redis
                                                ↕
                                        Payment Gateways (Stripe/Adyen)
```

### Key Database Tables

| Table | Description | Typical Size |
|---|---|---|
| `order_order` | All orders | 100K-10M rows |
| `checkout_checkout` | Active shopping carts | 10K-100K rows |
| `payment_payment` | Payment records | 100K-5M rows |
| `product_product` | Product catalog | 1K-100K rows |
| `product_productvariant` | Product SKU variants | 5K-500K rows |
| `warehouse_stock` | Inventory levels | 10K-1M rows |

### Common Data Flows

#### Checkout → Order Flow
1. Customer creates a Checkout
2. Adds lines (product variants + quantities)
3. Sets shipping/billing addresses
4. Selects shipping method
5. Provides payment details
6. Calls `checkoutComplete` mutation
7. System processes payment via gateway
8. Creates Order + OrderLines
9. Decrements stock
10. Sends confirmation email via Celery

#### Stock Management Flow
1. Product created → Stock records created per warehouse
2. Order placed → `quantity_allocated` incremented
3. Order fulfilled → `quantity` decremented, `quantity_allocated` decremented
4. Order canceled → `quantity_allocated` decremented (stock restored)

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | Django secret key | required |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost` |
| `DEFAULT_CURRENCY` | Default store currency | `USD` |
| `DEFAULT_COUNTRY` | Default country code | `US` |
| `STRIPE_SECRET_KEY` | Stripe API key | optional |
| `CELERY_BROKER_URL` | Celery broker URL | same as REDIS_URL |
