-- ============================================================================
-- Migration: Add exchange column to clientes table
-- Date: 2026-05-07
-- Purpose: Add support for multiple exchanges (Bybit and Binance)
-- ============================================================================

-- Add exchange column if it doesn't exist (defaults to 'bybit' for backward compatibility)
ALTER TABLE public.clientes 
ADD COLUMN IF NOT EXISTS exchange TEXT NOT NULL DEFAULT 'bybit';

-- Ensure all existing records have a valid exchange value
UPDATE public.clientes
SET exchange = 'bybit'
WHERE exchange IS NULL OR BTRIM(exchange) = '';

-- Add a check constraint to ensure only valid exchanges are stored
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'clientes_exchange_check'
    ) THEN
        ALTER TABLE public.clientes 
        ADD CONSTRAINT clientes_exchange_check 
        CHECK (exchange IN ('bybit', 'binance'));
    END IF;
END $$;

-- Create an index for better query performance
CREATE INDEX IF NOT EXISTS idx_clientes_exchange ON public.clientes(exchange);

-- Display migration summary
DO $$ 
DECLARE
    total_records INT;
    bybit_count INT;
    binance_count INT;
BEGIN
    SELECT COUNT(*) INTO total_records FROM public.clientes;
    SELECT COUNT(*) INTO bybit_count FROM public.clientes WHERE exchange = 'bybit';
    SELECT COUNT(*) INTO binance_count FROM public.clientes WHERE exchange = 'binance';
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Exchange Column Migration Complete';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Total records: %', total_records;
    RAISE NOTICE 'Bybit clients: %', bybit_count;
    RAISE NOTICE 'Binance clients: %', binance_count;
    RAISE NOTICE '========================================';
END $$;
