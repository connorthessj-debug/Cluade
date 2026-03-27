const express = require('express');
const http = require('http');
const path = require('path');
const { WebSocketServer } = require('ws');
const Database = require('better-sqlite3');

const app = express();
const PORT = process.env.PORT || 8080;
const DB_PATH = path.resolve(__dirname, '..', 'data', 'trading.db');

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------
let db;
try {
  db = new Database(DB_PATH, { readonly: false, fileMustExist: false });
  db.pragma('journal_mode = WAL');
  db.pragma('busy_timeout = 5000');
  console.log(`[DB] Connected to ${DB_PATH}`);
} catch (err) {
  console.warn(`[DB] Could not open database at ${DB_PATH}: ${err.message}`);
  console.warn('[DB] Dashboard will run with no data until the database is available.');
  db = null;
}

// Expose db to routes via app.locals
app.locals.db = db;

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ---------------------------------------------------------------------------
// API routes
// ---------------------------------------------------------------------------
const apiRouter = require('./routes/api');
app.use('/api', apiRouter);

// Fallback – serve index.html for any unknown GET (SPA)
app.get('*', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ---------------------------------------------------------------------------
// HTTP + WebSocket server
// ---------------------------------------------------------------------------
const server = http.createServer(app);

const wss = new WebSocketServer({ noServer: true });

// Track connected clients
const clients = new Set();

server.on('upgrade', (request, socket, head) => {
  wss.handleUpgrade(request, socket, head, (ws) => {
    wss.emit('connection', ws, request);
  });
});

wss.on('connection', (ws) => {
  clients.add(ws);
  console.log(`[WS] Client connected (${clients.size} total)`);

  // Send a snapshot of current state
  const snapshot = buildSnapshot();
  ws.send(JSON.stringify({ type: 'snapshot', data: snapshot }));

  ws.on('close', () => {
    clients.delete(ws);
    console.log(`[WS] Client disconnected (${clients.size} total)`);
  });

  ws.on('error', (err) => {
    console.error('[WS] Client error:', err.message);
    clients.delete(ws);
  });
});

/**
 * Broadcast a message to every connected WebSocket client.
 */
function broadcast(message) {
  const payload = typeof message === 'string' ? message : JSON.stringify(message);
  for (const client of clients) {
    if (client.readyState === 1) { // WebSocket.OPEN
      client.send(payload);
    }
  }
}

// Expose broadcast so routes or external callers can use it
app.locals.broadcast = broadcast;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildSnapshot() {
  if (!db) {
    return { bots: [], positions: [], recentTrades: [], summary: {} };
  }

  const snapshot = {};

  try {
    snapshot.bots = db.prepare(
      "SELECT * FROM bot_state ORDER BY name"
    ).all();
  } catch (_) { snapshot.bots = []; }

  try {
    snapshot.positions = db.prepare(
      "SELECT * FROM positions WHERE status = 'open' ORDER BY open_time DESC"
    ).all();
  } catch (_) { snapshot.positions = []; }

  try {
    snapshot.recentTrades = db.prepare(
      "SELECT * FROM trades ORDER BY close_time DESC LIMIT 50"
    ).all();
  } catch (_) { snapshot.recentTrades = []; }

  try {
    const row = db.prepare(
      "SELECT COUNT(*) as count, SUM(pnl) as total_pnl, " +
      "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins " +
      "FROM trades"
    ).get();
    snapshot.summary = {
      tradeCount: row.count || 0,
      totalPnl: row.total_pnl || 0,
      winRate: row.count > 0 ? ((row.wins / row.count) * 100) : 0
    };
  } catch (_) {
    snapshot.summary = { tradeCount: 0, totalPnl: 0, winRate: 0 };
  }

  return snapshot;
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
server.listen(PORT, () => {
  console.log(`[Server] Dashboard running at http://localhost:${PORT}`);
});

module.exports = { app, server, wss, broadcast };
