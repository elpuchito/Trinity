"""
Saleor Product Models — Synthetic representative code.

Defines Product, ProductVariant, Stock, and related models.
Products represent catalog items; variants handle SKU-level differentiation.
"""

from django.db import models
from decimal import Decimal


class Product(models.Model):
    """
    A product in the catalog.
    
    Products are the top-level catalog entity. Each product has one or more
    ProductVariants (e.g., size/color combinations).
    
    INCIDENT PATTERNS:
    - Product visible in search but returns 404 on product page:
      Channel assignment missing. Product must be published AND assigned to 
      the active channel.
    - Product shows wrong price: Check ProductChannelListing.currency matches
      the channel's default currency.
    """
    name = models.CharField(max_length=250)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    product_type = models.ForeignKey(
        "ProductType", related_name="products", on_delete=models.CASCADE,
    )
    category = models.ForeignKey(
        "Category", related_name="products", blank=True, null=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    weight = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    
    is_published = models.BooleanField(default=False)
    
    class Meta:
        ordering = ("slug",)
    
    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    """
    A specific variant of a product (e.g., "Blue / Medium").
    
    Each variant has its own SKU, price, and stock quantity.
    
    INCIDENT PATTERNS:
    - "Product not available" error during checkout:
      Check ProductVariant.track_inventory flag. If True, Stock records
      must exist and have quantity > 0.
    - SKU collision: Two variants with the same SKU causes GraphQL errors
      on product queries. SKUs should be unique across all variants.
    """
    product = models.ForeignKey(
        Product, related_name="variants", on_delete=models.CASCADE,
    )
    sku = models.CharField(max_length=255, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    
    # Pricing
    price_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    cost_price_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"), null=True, blank=True,
    )
    currency = models.CharField(max_length=3, default="USD")
    
    # Inventory
    track_inventory = models.BooleanField(default=True)
    weight = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sku",)

    def __str__(self):
        return f"{self.product.name} - {self.name}" if self.name else self.product.name


class Stock(models.Model):
    """
    Stock record linking a ProductVariant to a Warehouse with quantity.
    
    CRITICAL INCIDENT PATTERNS:
    
    1. Stock desynchronization:
       Stock.quantity in Saleor DB doesn't match the warehouse management
       system (WMS). Common causes:
       - WMS webhook failed to update Saleor
       - Manual stock adjustment in WMS not reflected in Saleor
       - Race condition during concurrent order fulfillments
       
       Diagnosis: Run the stock reconciliation report:
       SELECT v.sku, s.quantity, s.quantity_allocated 
       FROM stock s JOIN product_variant v ON s.product_variant_id = v.id
       WHERE s.quantity < s.quantity_allocated;
       
    2. Negative stock:
       Stock.quantity can go negative if two fulfillments decrement
       simultaneously without proper locking. The DB doesn't have a
       CHECK constraint on quantity >= 0 (by design, to allow backorders).
       
    3. Phantom stock:
       Stock record exists with quantity > 0, but the warehouse is
       deactivated. Product shows "in stock" but can't be fulfilled.
       Query: Stock.objects.filter(warehouse__is_active=False, quantity__gt=0)
    """
    warehouse = models.ForeignKey(
        "Warehouse", related_name="stock_entries", on_delete=models.CASCADE,
    )
    product_variant = models.ForeignKey(
        ProductVariant, related_name="stocks", on_delete=models.CASCADE,
    )
    quantity = models.IntegerField(default=0)
    quantity_allocated = models.IntegerField(default=0)

    class Meta:
        unique_together = ("warehouse", "product_variant")

    def __str__(self):
        return f"Stock: {self.product_variant.sku} @ {self.warehouse} = {self.quantity}"

    @property
    def available_quantity(self):
        """Quantity available for new orders.
        
        WARNING: Can be negative if quantity_allocated > quantity.
        Callers should check for negative values.
        """
        return self.quantity - self.quantity_allocated


class Warehouse(models.Model):
    """Physical warehouse location."""
    name = models.CharField(max_length=250)
    slug = models.SlugField(max_length=255, unique=True)
    address = models.ForeignKey(
        "account.Address", on_delete=models.PROTECT,
    )
    email = models.EmailField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
