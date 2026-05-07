# Deployment Instructions for Binance Support

## Quick Start Guide

This guide will help you deploy the updated Motor Sniper V60.7 with full Binance and Bybit support on Railway.

## Prerequisites

- Access to your Supabase dashboard
- Access to your Railway deployment (web-production-cc471.up.railway.app)
- Supabase credentials configured in your Railway environment variables

## Step-by-Step Deployment

### Step 1: Apply Database Migration (⚠️ REQUIRED FIRST)

You **must** apply the database migration before deploying the code. Otherwise, the application will fail to save exchange information.

#### Option A: Using Supabase SQL Editor (Recommended)

1. Go to your Supabase project dashboard: https://app.supabase.com
2. Navigate to **SQL Editor** in the left sidebar
3. Click **New Query**
4. Copy the contents of `tools/migrate_add_exchange_column.sql`
5. Paste into the SQL editor
6. Click **Run** (or press Ctrl+Enter)
7. You should see output showing:
   ```
   ========================================
   Exchange Column Migration Complete
   ========================================
   Total records: X
   Bybit clients: X
   Binance clients: 0
   ========================================
   ```

#### Option B: Using psql Command Line

```bash
# From the project root directory
psql -h YOUR_SUPABASE_HOST -U postgres -d postgres -f tools/migrate_add_exchange_column.sql
```

Replace `YOUR_SUPABASE_HOST` with your Supabase database host (found in your Supabase project settings under "Database").

### Step 2: Verify Migration Success

Run this SQL query in Supabase SQL Editor to verify:

```sql
-- Check if the column exists
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'clientes' AND column_name = 'exchange';

-- Should return:
-- column_name | data_type | column_default
-- exchange    | text      | 'bybit'::text
```

### Step 3: Deploy to Railway

Now that the database is ready, deploy the updated code:

#### Option A: Automatic Deployment (if connected to GitHub)

1. Push the changes to your GitHub repository (already done if you're reading this)
2. Railway will automatically detect the changes and redeploy
3. Monitor the deployment logs in Railway dashboard
4. Wait for "Deployment successful" message

#### Option B: Manual Deployment

1. Go to your Railway project: https://railway.app/project/YOUR_PROJECT_ID
2. Click on your service (web-production-cc471)
3. Go to **Deployments** tab
4. Click **Deploy** and select the branch with the updates
5. Monitor the deployment logs
6. Wait for "Deployment successful" message

### Step 4: Verify the Deployment

After Railway deployment completes:

1. **Open the application**: Go to https://web-production-cc471.up.railway.app
2. **Navigate to Gestão tab** (Management)
3. **Click "+ Novo Investidor"** (New Investor)
4. **Verify the form shows**:
   - ✅ **Corretora** section with both options:
     - 🟡 Bybit
     - 🟠 Binance
   - ✅ **Modo da Conta** section with both options:
     - 🛰️ Conta Testnet
     - 💼 Conta Real

### Step 5: Test Binance Integration

Create a test Binance client:

1. Click **"+ Novo Investidor"**
2. Select **"🟠 Binance"** as the exchange
3. Select **"🛰️ Conta Testnet"** as account mode
4. Fill in:
   - **Nome do Cliente**: "Test Binance"
   - **API Key Binance**: Your Binance Futures Testnet API key
   - **API Secret Binance**: Your Binance Futures Testnet API secret
   - Leave Telegram fields empty (optional)
5. Click **"Guardar Investidor"**
6. Wait for validation
7. **Expected Result**: 
   - ✅ Success message: "Conta Binance TESTNET validada OK"
   - ✅ Client appears in the list with **"BINANCE"** orange badge
   - ✅ Balance is automatically fetched from Binance

### Step 6: Verify Existing Clients

Check that existing clients still work:

1. Go to the **Gestão** tab
2. **Verify existing clients show**:
   - ✅ **"BYBIT"** yellow badge (default for all existing clients)
   - ✅ **"CONTA REAL"** or **"CONTA TESTNET"** green/blue badge
   - ✅ **"SUPABASE"** badge if synced from cloud
3. Click **Settings icon** on an existing client
4. **Verify you can**:
   - ✅ Change exchange from Bybit to Binance (or vice versa)
   - ✅ Update credentials
   - ✅ Save changes successfully

## Troubleshooting

### Issue: Migration fails with "column already exists"

**Solution**: The column already exists. This is safe to ignore. The migration uses `ADD COLUMN IF NOT EXISTS` to be idempotent.

### Issue: Railway deployment fails

**Possible causes**:
1. **Database not migrated first**: Apply the migration (Step 1) before deploying
2. **Environment variables missing**: Verify `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` are set in Railway
3. **Build error**: Check Railway logs for specific error messages

### Issue: Binance clients show as "Bybit"

**Possible causes**:
1. **Migration not applied**: Go back to Step 1 and apply the migration
2. **Cache issue**: Clear your browser cache and refresh the page
3. **Old deployment**: Ensure the latest code is deployed to Railway

### Issue: "API inválida" error when saving Binance client

**Possible causes**:
1. **Wrong API keys**: Verify you're using Binance **Futures** API keys (not Spot)
2. **Testnet vs Real mismatch**: If using Testnet mode, ensure you have Binance Futures **Testnet** keys
3. **API key permissions**: Ensure the API key has "Enable Reading" and "Enable Futures" permissions

## Getting Binance API Keys

### For Testnet (Recommended for Testing)

1. Go to: https://testnet.binancefuture.com
2. Register with your GitHub account
3. Go to **API Key** section
4. Create a new API key
5. Copy both the **API Key** and **Secret Key**
6. Use these in the Motor Sniper form with **Testnet** mode selected

### For Production (Real Trading)

1. Go to: https://www.binance.com
2. Login to your account
3. Go to **API Management**
4. Create a new API key for **Futures Trading**
5. Enable permissions: "Enable Reading" and "Enable Futures"
6. Copy both the **API Key** and **Secret Key**
7. Use these in the Motor Sniper form with **Real** mode selected

## Rollback Instructions

If something goes wrong and you need to rollback:

### Rollback Code (Railway)

1. Go to Railway dashboard
2. Navigate to **Deployments** tab
3. Find the previous working deployment
4. Click **Redeploy** on that version

### Rollback Database (Not Recommended)

⚠️ **Warning**: Only do this if absolutely necessary. You will lose exchange information for all clients.

```sql
-- Remove the index
DROP INDEX IF EXISTS idx_clientes_exchange;

-- Remove the constraint
ALTER TABLE public.clientes DROP CONSTRAINT IF EXISTS clientes_exchange_check;

-- Remove the column
ALTER TABLE public.clientes DROP COLUMN IF EXISTS exchange;
```

## Support

For issues or questions:

1. **Check application logs**: Railway → Deployments → View Logs
2. **Check Supabase logs**: Supabase → Logs & Monitoring
3. **Review migration documentation**: `docs/EXCHANGE_MIGRATION.md`
4. **Contact support**: Open an issue on GitHub

## Success Checklist

After deployment, verify:

- ✅ Migration applied successfully in Supabase
- ✅ Railway deployment successful
- ✅ Application loads without errors
- ✅ Form shows both Bybit and Binance options
- ✅ Can create new Bybit clients
- ✅ Can create new Binance clients
- ✅ Existing clients show correct badges
- ✅ Can edit clients and change exchange
- ✅ Balance syncs correctly for both exchanges

## Next Steps

Once deployment is verified:

1. **Test thoroughly** with testnet accounts first
2. **Monitor the logs** for any errors
3. **Create real clients** only after testnet validation
4. **Keep the migration script** for future reference

---

**Version**: Motor Sniper V60.7  
**Date**: 2026-05-07  
**Server**: web-production-cc471.up.railway.app
