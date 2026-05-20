# 🚀 Render.com Deployment Guide

## Quick Setup

### Basic Configuration

```
Name: ai-sniper-bybit-v5-master
Language: Python 3
Branch: main
Region: Singapore (Southeast Asia)
Root Directory: (leave empty)
```

### Build & Start Commands

**Build Command:**
```bash
pip install -r requirements.txt && npm ci && npm run build
```

**Start Command:**
```bash
gunicorn -w 2 -k gthread --threads 8 -b 0.0.0.0:$PORT main_web:app
```

## Environment Variables

### Core Configuration
```
ENVIRONMENT=production
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true
USE_TESTNET=false
PORT=10000
```

### Bybit Credentials
```
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret
```

### AI APIs
```
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
```

### Telegram Notifications
```
TELEGRAM_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

### Frontend
```
VITE_API_BASE=https://your-app-name.onrender.com
```

### Optional 2FA
```
TOTP_SECRET=
TOTP_CODE=
```

### **CRITICAL: Database Path**
```
SQLITE_DB_PATH=/tmp/ai-sniper/database.db
```
⚠️ **IMPORTANT**: Render's `/app` directory is READ-ONLY. You MUST set this variable or database initialization will fail with "Permission denied" error.

## Instance Types

- **Free ($0/mo)**: 512 MB RAM, 0.1 CPU - Testing only
- **Starter ($7/mo)**: 512 MB RAM, 0.5 CPU - Minimum for production
- **Standard ($25/mo)**: 2 GB RAM, 1 CPU - Recommended for trading

## Important Notes

### ⚠️ CRITICAL: Fix "Permission denied: '/app'" Error

**The Problem:**
Render's `/app` directory is READ-ONLY. The default database path `/app/data/database.db` will fail with:
```
PermissionError: [Errno 13] Permission denied: '/app'
```

**The Solution:**
Add this environment variable:
```
SQLITE_DB_PATH=/tmp/ai-sniper/database.db
```

### Data Persistence
⚠️ **WARNING**: `/tmp` storage is EPHEMERAL - all data is lost on restart!

For production with persistent data, you have two options:

**Option 1: Render Persistent Disk (Recommended)**
1. Go to your service → "Disks" tab
2. Add new disk: Name: `data`, Mount Path: `/data`, Size: 1GB
3. Set environment variable: `SQLITE_DB_PATH=/data/database.db`

**Option 2: External Database**
- Migrate to PostgreSQL or other managed database
- Use Render's free PostgreSQL addon

### Blueprint Deployment
Use Infrastructure as Code with existing `render.yaml`:
1. Go to Render Dashboard → "Blueprint" → "New Blueprint Instance"
2. Connect GitHub repository
3. Render auto-detects `render.yaml` configuration

### Python Runtime
- Configured in `runtime.txt`: `python-3.11.9`
- Node.js required for frontend build (`npm ci && npm run build`)

## Health Checks
Configure health check endpoint at `/` or `/health` if available.
