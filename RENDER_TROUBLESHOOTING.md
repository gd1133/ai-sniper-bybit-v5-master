# 🔧 Render Deployment Troubleshooting

## Common Errors & Solutions

### ❌ Error: `PermissionError: [Errno 13] Permission denied: '/app'`

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/app'
File "/opt/render/project/src/src/database/manager.py", line 79, in init_db
    os.makedirs(db_dir, exist_ok=True)
```

**Cause:**
Render's `/app` directory is READ-ONLY. The application cannot create `/app/data` for the database.

**Solution:**
Add environment variable in Render Dashboard:
```
SQLITE_DB_PATH=/tmp/ai-sniper/database.db
```

**Steps:**
1. Go to your Render service → Environment tab
2. Add new variable: `SQLITE_DB_PATH` = `/tmp/ai-sniper/database.db`
3. Click "Save Changes" → Service will auto-redeploy
4. Check logs - should see: `📂 [DATABASE] Usando SQLITE_DB_PATH: /tmp/ai-sniper/database.db`

---

### ❌ Error: `gunicorn: command not found` or `npm: command not found`

**Cause:**
Build command not installing dependencies properly.

**Solution:**
Verify Build Command is:
```bash
pip install -r requirements.txt && npm ci && npm run build
```

**Start Command should be:**
```bash
gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:$PORT --timeout 120 main_web:app
```

---

### ❌ Error: Import errors or module not found

**Symptom:**
```
ModuleNotFoundError: No module named 'src'
ModuleNotFoundError: No module named 'ccxt'
```

**Solution:**
1. Verify `requirements.txt` exists and has all dependencies
2. Check Build Command runs `pip install -r requirements.txt`
3. Verify Python version: runtime.txt should have `python-3.11.9`

---

### ⚠️ Warning: Data loss on restart

**Problem:**
Using `/tmp` means ALL DATA IS LOST when service restarts.

**Solution for Production:**

**Option 1: Add Persistent Disk**
1. Service → Disks tab → "Add Disk"
2. Name: `data`, Mount Path: `/data`, Size: 1GB
3. Update env var: `SQLITE_DB_PATH=/data/database.db`
4. Redeploy service

**Option 2: Use Managed Database**
- Add PostgreSQL addon from Render
- Migrate code to use PostgreSQL instead of SQLite

---

### ❌ Error: `502 Bad Gateway` or service won't start

**Causes:**
1. Application crashes on startup
2. Wrong start command
3. Port binding issues
4. Missing environment variables

**Debug Steps:**

1. **Check Logs:**
   - Render Dashboard → Logs tab
   - Look for Python traceback or error messages

2. **Verify Start Command:**
   ```bash
   gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:$PORT --timeout 120 main_web:app
   ```

3. **Check Critical Environment Variables:**
   ```
   ENVIRONMENT=production
   ALLOW_ORDER_EXECUTION=true
   ALLOW_REAL_TRADING=true
   USE_TESTNET=false
   SQLITE_DB_PATH=/tmp/ai-sniper/database.db
   ```

4. **Verify API Keys are set:**
   - BYBIT_API_KEY
   - BYBIT_API_SECRET
   - GEMINI_API_KEY
   - GROQ_API_KEY

5. **Check Health Endpoint:**
   - After deploy, visit: `https://your-app.onrender.com/`
   - Should return dashboard or API response

---

## Quick Deployment Checklist

Before deploying, verify:

- [ ] **Build Command:** `pip install -r requirements.txt && npm ci && npm run build`
- [ ] **Start Command:** `gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:$PORT --timeout 120 main_web:app`
- [ ] **Python Version:** `runtime.txt` has `python-3.11.9`
- [ ] **Branch:** Set to `main` (or your production branch)
- [ ] **Region:** Singapore or Frankfurt for lower latency
- [ ] **Instance Type:** Starter ($7/mo) minimum for production

**Environment Variables:**
- [ ] `ENVIRONMENT=production`
- [ ] `SQLITE_DB_PATH=/tmp/ai-sniper/database.db` ⚠️ CRITICAL
- [ ] `ALLOW_ORDER_EXECUTION=true`
- [ ] `ALLOW_REAL_TRADING=true`
- [ ] `USE_TESTNET=false`
- [ ] `BYBIT_API_KEY` (your actual key)
- [ ] `BYBIT_API_SECRET` (your actual secret)
- [ ] `GEMINI_API_KEY` (optional for AI)
- [ ] `GROQ_API_KEY` (optional for AI)
- [ ] `TELEGRAM_TOKEN` (optional for notifications)
- [ ] `TELEGRAM_CHAT_ID` (optional for notifications)

---

## Getting Logs

**Method 1: Render Dashboard**
- Go to your service → Logs tab
- Live stream of application output

**Method 2: Render CLI**
```bash
render logs -s your-service-name
```

**Look for:**
- `📂 [DATABASE]` lines - database initialization
- `🔧 [ENV CONFIG]` lines - configuration validation
- Python traceback - error details
- `Listening at` - successful startup

---

## Still Having Issues?

1. Check this troubleshooting guide first
2. Review deployment logs carefully
3. Verify all environment variables are set correctly
4. Test locally with same environment variables
5. Check Render Status Page: https://status.render.com/

For repository-specific issues, check:
- `README.md` - general documentation
- `RENDER_DEPLOYMENT.md` - deployment guide
- `.env.example` - all available environment variables
