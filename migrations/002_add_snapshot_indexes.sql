-- Migration 002: Add indexes for snapshot search performance
-- Created: 2026-08-11
-- Description: Improves history search performance by indexing product_name_snapshot and sku_snapshot

CREATE INDEX IF NOT EXISTS idx_export_items_product_name ON export_order_items(product_name_snapshot);
CREATE INDEX IF NOT EXISTS idx_export_items_sku ON export_order_items(sku_snapshot);
