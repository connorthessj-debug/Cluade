const express = require('express');
const router = express.Router();

// ---------------------------------------------------------------------------
// Helper – safely run a DB query, return fallback on error
// ---------------------------------------------------------------------------
function safeQuery(db, fn, fallback) {
  if (!db) return fallback;
  try {
    return fn(db);
  } catch (err) {
    console.error('[API] Query error:', err.message);
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// GET /api/bots – list all bots with current status
// ---------------------------------------------------------------------------
router.get('/bots', (req, res) => {
  const db = req.app.locals.db;
  const bots = safeQuery(db, (d) => d.prepare("SELECT * FROM bot_state ORDER BY name").all(), []);
  res.json(bots);
});

// ---------------------------------------------------------------------------
// GET /api/trades – list trades with query params
// ---------------------------------------------------------------------------
router.get('/trades', (req, res) => {
  const db = req.app.locals.db;
  const { bot, symbol, limit = 50, offset = 0 } = req.query;

  const result = safeQuery(db, (d) => {
    let sql = "SELECT * FROM trades WHERE 1=1";
    const params = {};

    if (bot) {
      sql += " AND bot = @bot";
      params.bot = bot;
    }
    if (symbol) {
      sql += " AND symbol = @symbol";
      params.symbol = symbol;
    }

    sql += " ORDER BY close_time DESC LIMIT @limit OFFSET @offset";
    params.limit = parseInt(limit, 10);
    params.offset = parseInt(offset, 10);

    return d.prepare(sql).all(params);
  }, []);

  res.json(result);
});

// ---------------------------------------------------------------------------
// GET /api/trades/summary – aggregate stats per bot
// ---------------------------------------------------------------------------
router.get('/trades/summary', (req, res) => {
  const db = req.app.locals.db;
  const summary = safeQuery(db, (d) => {
    return d.prepare(`
      SELECT
        bot,
        COUNT(*) as trade_count,
        SUM(pnl) as total_pnl,
        AVG(pnl) as avg_pnl,
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
        ROUND(CAST(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 2) as win_rate,
        MAX(pnl) as best_trade,
        MIN(pnl) as worst_trade
      FROM trades
      GROUP BY bot
      ORDER BY total_pnl DESC
    `).all();
  }, []);

  // Also compute totals
  const totals = safeQuery(db, (d) => {
    return d.prepare(`
      SELECT
        COUNT(*) as trade_count,
        SUM(pnl) as total_pnl,
        AVG(pnl) as avg_pnl,
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
        ROUND(CAST(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 2) as win_rate
      FROM trades
    `).get();
  }, { trade_count: 0, total_pnl: 0, avg_pnl: 0, wins: 0, win_rate: 0 });

  res.json({ bots: summary, totals });
});

// ---------------------------------------------------------------------------
// GET /api/pnl – P&L data for charting
// ---------------------------------------------------------------------------
router.get('/pnl', (req, res) => {
  const db = req.app.locals.db;
  const { interval = 'daily', bot } = req.query;

  const groupExpr = interval === 'hourly'
    ? "strftime('%Y-%m-%d %H:00', close_time)"
    : "strftime('%Y-%m-%d', close_time)";

  const result = safeQuery(db, (d) => {
    let sql = `
      SELECT
        ${groupExpr} as period,
        SUM(pnl) as pnl,
        COUNT(*) as trades
      FROM trades
      WHERE close_time IS NOT NULL
    `;
    const params = {};
    if (bot) {
      sql += " AND bot = @bot";
      params.bot = bot;
    }
    sql += " GROUP BY period ORDER BY period ASC";
    return d.prepare(sql).all(params);
  }, []);

  // Compute cumulative
  let cumulative = 0;
  const withCumulative = result.map((row) => {
    cumulative += row.pnl || 0;
    return { ...row, cumulative_pnl: cumulative };
  });

  res.json(withCumulative);
});

// ---------------------------------------------------------------------------
// GET /api/positions – current open positions
// ---------------------------------------------------------------------------
router.get('/positions', (req, res) => {
  const db = req.app.locals.db;
  const positions = safeQuery(db, (d) => {
    return d.prepare(
      "SELECT * FROM positions WHERE status = 'open' ORDER BY open_time DESC"
    ).all();
  }, []);
  res.json(positions);
});

// ---------------------------------------------------------------------------
// GET /api/events – recent events
// ---------------------------------------------------------------------------
router.get('/events', (req, res) => {
  const db = req.app.locals.db;
  const limit = parseInt(req.query.limit, 10) || 100;
  const events = safeQuery(db, (d) => {
    return d.prepare(
      "SELECT * FROM events ORDER BY id DESC LIMIT @limit"
    ).all({ limit });
  }, []);
  res.json(events);
});

// ---------------------------------------------------------------------------
// GET /api/performance – performance metrics
// ---------------------------------------------------------------------------
router.get('/performance', (req, res) => {
  const db = req.app.locals.db;
  const metrics = safeQuery(db, (d) => {
    return d.prepare("SELECT * FROM performance_metrics ORDER BY timestamp DESC LIMIT 100").all();
  }, []);
  res.json(metrics);
});

// ---------------------------------------------------------------------------
// GET /api/learning – learning engine stats
// ---------------------------------------------------------------------------
router.get('/learning', (req, res) => {
  const db = req.app.locals.db;

  const stats = safeQuery(db, (d) => {
    let patternsCount = 0;
    let lastOptimization = null;
    let recommendations = [];

    try {
      const pc = d.prepare("SELECT COUNT(*) as count FROM learned_patterns").get();
      patternsCount = pc.count;
    } catch (_) {}

    try {
      const lo = d.prepare(
        "SELECT timestamp FROM optimization_runs ORDER BY timestamp DESC LIMIT 1"
      ).get();
      lastOptimization = lo ? lo.timestamp : null;
    } catch (_) {}

    try {
      recommendations = d.prepare(
        "SELECT * FROM recommendations ORDER BY created_at DESC LIMIT 20"
      ).all();
    } catch (_) {}

    return { patternsCount, lastOptimization, recommendations };
  }, { patternsCount: 0, lastOptimization: null, recommendations: [] });

  res.json(stats);
});

// ---------------------------------------------------------------------------
// POST /api/bots/:name/toggle – toggle bot running state
// ---------------------------------------------------------------------------
router.post('/bots/:name/toggle', (req, res) => {
  const db = req.app.locals.db;
  const { name } = req.params;

  if (!db) {
    return res.status(503).json({ error: 'Database not available' });
  }

  try {
    const bot = db.prepare("SELECT * FROM bot_state WHERE name = @name").get({ name });
    if (!bot) {
      return res.status(404).json({ error: `Bot '${name}' not found` });
    }

    const newStatus = bot.status === 'running' ? 'stopped' : 'running';
    db.prepare("UPDATE bot_state SET status = @status, updated_at = datetime('now') WHERE name = @name")
      .run({ status: newStatus, name });

    const updated = db.prepare("SELECT * FROM bot_state WHERE name = @name").get({ name });

    // Broadcast the change
    const broadcast = req.app.locals.broadcast;
    if (broadcast) {
      broadcast({ type: 'bot_update', data: updated });
    }

    res.json(updated);
  } catch (err) {
    console.error('[API] Toggle error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ---------------------------------------------------------------------------
// POST /api/bots/:name/settings – update bot settings
// ---------------------------------------------------------------------------
router.post('/bots/:name/settings', (req, res) => {
  const db = req.app.locals.db;
  const { name } = req.params;
  const settings = req.body;

  if (!db) {
    return res.status(503).json({ error: 'Database not available' });
  }

  try {
    db.prepare(
      "UPDATE bot_state SET settings = @settings, updated_at = datetime('now') WHERE name = @name"
    ).run({ settings: JSON.stringify(settings), name });

    const updated = db.prepare("SELECT * FROM bot_state WHERE name = @name").get({ name });
    res.json(updated);
  } catch (err) {
    console.error('[API] Settings update error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
