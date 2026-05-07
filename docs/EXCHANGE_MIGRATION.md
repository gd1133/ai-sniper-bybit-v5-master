# Database Migration: Add Exchange Support

## Overview
This migration adds support for multiple cryptocurrency exchanges (Bybit and Binance) to the Motor Sniper V60.7 trading system.

## Problem
The system was only displaying "BYBIT" for all investors because the Supabase database schema was missing the `exchange` column, even though the application code already supported both Bybit and Binance exchanges.

## Solution
Added the `exchange` column to the `clientes` table in Supabase with proper defaults and validation.

## What Changed

### 1. Database Schema (`tools/supabase_schema.sql`)
- Added `exchange TEXT NOT NULL DEFAULT 'bybit'` column to `clientes` table
- Added data migration to set existing records to 'bybit' for backward compatibility

### 2. Supabase Manager (`src/database/supabase_manager.py`)
- Updated `_prepare_client_payload()` to include `exchange` field when saving clients
- Updated `_normalize_client_row()` to handle `exchange` field with proper defaults

### 3. Migration Script (`tools/migrate_add_exchange_column.sql`)
- Standalone SQL script to add the exchange column to existing databases
- Includes validation constraint to ensure only 'bybit' or 'binance' values are stored
- Creates an index for better query performance

## How to Apply the Migration

### Option 1: For New Installations
Simply run the updated `tools/supabase_schema.sql` script:

```bash
psql -h YOUR_SUPABASE_HOST -U postgres -d postgres -f tools/supabase_schema.sql
```

Or use the Supabase SQL Editor and paste the contents of `supabase_schema.sql`.

### Option 2: For Existing Installations
Run the migration script on your existing database:

```bash
psql -h YOUR_SUPABASE_HOST -U postgres -d postgres -f tools/migrate_add_exchange_column.sql
```

Or use the Supabase SQL Editor and paste the contents of `migrate_add_exchange_column.sql`.

### Using Supabase Dashboard
1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Create a new query
4. Paste the contents of `tools/migrate_add_exchange_column.sql`
5. Click **Run**

The migration will:
- ✅ Add the `exchange` column if it doesn't exist
- ✅ Set all existing records to 'bybit' (default for backward compatibility)
- ✅ Add validation to ensure only 'bybit' or 'binance' values are allowed
- ✅ Create an index for better performance
- ✅ Display a summary of the migration

## Verification

After applying the migration, verify it worked by running:

```sql
-- Check if the column exists
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'clientes' AND column_name = 'exchange';

-- Check the distribution of exchanges
SELECT exchange, COUNT(*) as count 
FROM public.clientes 
GROUP BY exchange;
```

## Testing

1. **Create a new Bybit client** through the web interface:
   - Select "🟡 Bybit" as the exchange
   - Fill in the credentials
   - Save
   - Verify the client shows "BYBIT" badge in the investor list

2. **Create a new Binance client** through the web interface:
   - Select "🟠 Binance" as the exchange
   - Fill in the Binance Futures credentials
   - Save
   - Verify the client shows "BINANCE" badge in the investor list

3. **Check existing clients**:
   - All existing clients should show "BYBIT" badge (default value)
   - You can edit them and change to Binance if needed

## Important Notes

- **Backward Compatibility**: All existing clients will default to 'bybit' exchange
- **API Key Fields**: The system uses `bybit_key` and `bybit_secret` column names for BOTH Bybit and Binance credentials (this is intentional for backward compatibility)
- **Testnet Support**: Both exchanges support testnet mode:
  - Bybit: Uses Bybit Testnet Sandbox
  - Binance: Uses Binance Futures Testnet
- **No Data Loss**: This migration is safe and non-destructive

## Rollback

If you need to rollback this migration (remove the exchange column):

```sql
-- Remove the index
DROP INDEX IF EXISTS idx_clientes_exchange;

-- Remove the constraint
ALTER TABLE public.clientes DROP CONSTRAINT IF EXISTS clientes_exchange_check;

-- Remove the column
ALTER TABLE public.clientes DROP COLUMN IF EXISTS exchange;
```

**⚠️ Warning**: Rolling back will remove exchange information. Make a backup first!

## Railway Deployment

When deploying to Railway (web-production-cc471.up.railway.app):

1. The migration needs to be applied to your Supabase database first
2. Then deploy the updated code to Railway
3. Railway will automatically use the new schema on the next restart

## Support

For issues or questions:
- Check the application logs for any Supabase connection errors
- Verify your Supabase credentials are correct in the `.env` file
- Ensure you're using the service_role key (not anon key) for database operations

## Version
- **Created**: 2026-05-07
- **Motor Sniper Version**: V60.7
- **Schema Version**: 1.1.0
