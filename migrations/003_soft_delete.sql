-- Migration 003: Add soft delete for products
-- Created: 2026-08-11
-- Description: Add deleted_at column for soft delete functionality

ALTER TABLE products ADD COLUMN deleted_at TEXT;
