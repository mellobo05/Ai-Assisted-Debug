# Phase 1 Quick Start Guide

## 🚀 Quick Setup (5 minutes)

### Step 1: Install Redis (Optional but Recommended)

**Windows (Docker):**
```powershell
docker run -d -p 6379:6379 --name redis redis:7-alpine
```

**Linux:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**Mac:**
```bash
brew install redis
brew services start redis
```

### Step 2: Install Python Dependencies

```powershell
pip install -r requirement.txt
```

### Step 3: Update `.env`

Add these lines to your `.env` file:

```env
# Redis (optional - app works without it)
REDIS_HOST=localhost
REDIS_PORT=6379

# Database connection pool (optional - defaults work fine)
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

### Step 4: Start Server

```powershell
.\run_server.ps1
```

### Step 5: Test Health Endpoint

```powershell
curl http://localhost:8000/health
```

You should see:
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "embedding_provider": "gemini"
  }
}
```

---

## ✅ Verification Checklist

- [ ] Redis is running (`redis-cli ping` returns `PONG`)
- [ ] Health endpoint returns `"status": "healthy"`
- [ ] Server starts without errors
- [ ] First API request works
- [ ] Second identical request returns `"cache_hit": true`

---

## 📊 What Changed?

### Before Phase 1:
- Default connection pool (~5 connections)
- No caching (every request hits DB + LLM)
- No health monitoring

### After Phase 1:
- ✅ 20-60 concurrent database connections
- ✅ Redis caching (70-90% faster for repeated queries)
- ✅ Health check endpoint for monitoring

---

## 🎯 Expected Performance

| Metric | Before | After Phase 1 |
|--------|--------|---------------|
| Cache Hit Response | N/A | <10ms |
| Cache Miss Response | 2-5s | 2-5s (same) |
| Concurrent Connections | ~5 | 20-60 |
| Database Load | 100% | 10-30% (with caching) |

---

## 🔧 Troubleshooting

### Redis Not Working?
- App still works! Caching is just disabled
- Check: `redis-cli ping` should return `PONG`
- Verify `REDIS_HOST` and `REDIS_PORT` in `.env`

### Connection Pool Issues?
- Increase `DB_POOL_SIZE` in `.env`
- Check database max connections: `SHOW max_connections;`

### Health Check Failing?
- Check database connection string
- Verify Redis is accessible (if configured)
- Check server logs for details

---

## 📝 Next Steps

Once Phase 1 is working:

1. **Monitor cache hit rate** - Should be >70% for repeated queries
2. **Tune connection pool** - Adjust based on your load
3. **Set up monitoring** - Use `/health` endpoint with your monitoring tool
4. **Proceed to Phase 2** - Distributed job queue and vector database

---

## 💡 Pro Tips

1. **Redis is Optional**: The app works fine without Redis, just without caching
2. **Start Small**: Default pool sizes work for most cases
3. **Monitor First**: Watch metrics before tuning
4. **Cache TTL**: Analysis results cached for 1 hour (adjustable in code)

---

## 🆘 Need Help?

- Check `PHASE1_IMPLEMENTATION.md` for detailed documentation
- Review `SCALING_STRATEGY.md` for architecture overview
- Check server logs for error messages

---

**Phase 1 Complete!** 🎉
