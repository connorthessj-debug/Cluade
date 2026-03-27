/* ==========================================================================
   Main Application - Trading Bot Dashboard
   ========================================================================== */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Global State
  // ---------------------------------------------------------------------------
  var state = {
    bots: [],
    trades: [],
    positions: [],
    events: [],
    summary: { tradeCount: 0, totalPnl: 0, winRate: 0 },
    connected: false,
    activeTab: 'overview'
  };

  // ---------------------------------------------------------------------------
  // DOM References
  // ---------------------------------------------------------------------------
  var connectionStatus = document.getElementById('connection-status');
  var headerTotalPnl = document.getElementById('header-total-pnl');
  var headerWinRate = document.getElementById('header-win-rate');
  var headerTradeCount = document.getElementById('header-trade-count');
  var botCardsContainer = document.getElementById('bot-cards-container');
  var positionsList = document.getElementById('positions-list');
  var eventsFeed = document.getElementById('events-feed');
  var tradeTableContainer = document.getElementById('trade-table-container');
  var pnlChartContainer = document.getElementById('pnl-chart-container');
  var settingsContainer = document.getElementById('settings-panel-container');

  // ---------------------------------------------------------------------------
  // Tab Switching
  // ---------------------------------------------------------------------------
  var tabButtons = document.querySelectorAll('.tab-btn');
  var tabPanels = document.querySelectorAll('.tab-panel');

  tabButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var tab = btn.getAttribute('data-tab');
      switchTab(tab);
    });
  });

  function switchTab(tab) {
    state.activeTab = tab;

    tabButtons.forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === tab);
    });
    tabPanels.forEach(function (p) {
      p.classList.toggle('active', p.id === 'tab-' + tab);
    });

    // Lazy-init tabs on first view
    if (tab === 'trades' && !tradeTableContainer._tradeState) {
      TradeTable.createTradeTable(tradeTableContainer, state.trades, state.bots);
    }
    if (tab === 'analytics') {
      PnlChart.load(pnlChartContainer);
    }
    if (tab === 'settings') {
      SettingsPanel.init(settingsContainer);
    }

    // Resize charts when switching to a tab that has them
    setTimeout(function () { Charts.resizeAll(); }, 50);
  }

  // ---------------------------------------------------------------------------
  // WebSocket Connection
  // ---------------------------------------------------------------------------
  var wsConn = Utils.createWebSocket({
    onOpen: function () {
      state.connected = true;
      connectionStatus.className = 'connection-indicator connected';
      connectionStatus.querySelector('.status-text').textContent = 'Connected';
    },
    onClose: function () {
      state.connected = false;
      connectionStatus.className = 'connection-indicator disconnected';
      connectionStatus.querySelector('.status-text').textContent = 'Disconnected';
    },
    onMessage: function (msg) {
      handleWSMessage(msg);
    }
  });

  function handleWSMessage(msg) {
    if (!msg || !msg.type) return;

    switch (msg.type) {
      case 'snapshot':
        handleSnapshot(msg.data);
        break;
      case 'bot_update':
        handleBotUpdate(msg.data);
        break;
      case 'event':
        handleEvent(msg.data);
        break;
      case 'trade':
        handleNewTrade(msg.data);
        break;
      case 'position_update':
        handlePositionUpdate(msg.data);
        break;
      default:
        console.log('[WS] Unknown message type:', msg.type);
    }
  }

  // ---------------------------------------------------------------------------
  // Message Handlers
  // ---------------------------------------------------------------------------

  function handleSnapshot(data) {
    if (!data) return;

    if (data.bots) {
      state.bots = data.bots;
      BotCard.renderBotCards(botCardsContainer, state.bots);
    }

    if (data.positions) {
      state.positions = data.positions;
      renderPositions();
    }

    if (data.recentTrades) {
      state.trades = data.recentTrades;
      if (tradeTableContainer._tradeState) {
        TradeTable.updateTradeTable(tradeTableContainer, state.trades);
      }
    }

    if (data.summary) {
      state.summary = data.summary;
      updateHeaderStats();
    }

    // Build equity chart from snapshot if we have trade data
    loadEquityChart();
  }

  function handleBotUpdate(bot) {
    if (!bot) return;
    // Update local state
    var idx = state.bots.findIndex(function (b) { return b.name === bot.name; });
    if (idx >= 0) {
      state.bots[idx] = bot;
    } else {
      state.bots.push(bot);
    }
    BotCard.upsertBotCard(botCardsContainer, bot);
  }

  function handleEvent(event) {
    if (!event) return;
    state.events.unshift(event);
    if (state.events.length > 200) state.events.length = 200;
    prependEvent(event);

    // If the event is a trade, also refresh trades
    var etype = (event.event_type || '').toLowerCase();
    if (etype === 'trade' || etype === 'trade_closed') {
      refreshTrades();
    }
  }

  function handleNewTrade(trade) {
    if (!trade) return;
    state.trades.unshift(trade);
    if (tradeTableContainer._tradeState) {
      TradeTable.appendTrade(tradeTableContainer, trade);
    }
    // Refresh summary
    refreshSummary();
  }

  function handlePositionUpdate(position) {
    if (!position) return;
    refreshPositions();
  }

  // ---------------------------------------------------------------------------
  // Rendering Functions
  // ---------------------------------------------------------------------------

  function updateHeaderStats() {
    var pnl = state.summary.totalPnl || 0;
    headerTotalPnl.textContent = Utils.formatCurrencyPlain(pnl);
    headerTotalPnl.className = 'header-stat-value ' + (pnl >= 0 ? 'cell-positive' : 'cell-negative');

    headerWinRate.textContent = Utils.formatPercent(state.summary.winRate || 0);
    headerTradeCount.textContent = state.summary.tradeCount || 0;
  }

  function renderPositions() {
    if (!state.positions || state.positions.length === 0) {
      positionsList.innerHTML = '<p class="empty-state">No open positions</p>';
      return;
    }

    positionsList.innerHTML = '';
    state.positions.forEach(function (pos) {
      var item = document.createElement('div');
      item.className = 'position-item';

      var pnl = parseFloat(pos.unrealized_pnl || pos.pnl || 0);
      var side = (pos.side || 'long').toLowerCase();

      item.innerHTML =
        '<div>' +
          '<div class="position-symbol">' + escapeHtml(pos.symbol || '') + '</div>' +
          '<span class="position-side ' + side + '">' + side + '</span>' +
        '</div>' +
        '<div style="text-align:right">' +
          '<div class="position-pnl ' + (pnl >= 0 ? 'cell-positive' : 'cell-negative') + '">' +
            Utils.formatCurrencyPlain(pnl) +
          '</div>' +
          '<div style="font-size:0.72rem; color:var(--text-muted)">' + Utils.formatTime(pos.open_time) + '</div>' +
        '</div>';

      positionsList.appendChild(item);
    });
  }

  function renderEvents(events) {
    if (!events || events.length === 0) {
      eventsFeed.innerHTML = '<p class="empty-state">No recent events</p>';
      return;
    }

    eventsFeed.innerHTML = '';
    events.slice(0, 50).forEach(function (evt) {
      eventsFeed.appendChild(createEventItem(evt));
    });
  }

  function prependEvent(evt) {
    // Remove empty state
    var empty = eventsFeed.querySelector('.empty-state');
    if (empty) empty.remove();

    var item = createEventItem(evt);
    Utils.flashElement(item);

    if (eventsFeed.firstChild) {
      eventsFeed.insertBefore(item, eventsFeed.firstChild);
    } else {
      eventsFeed.appendChild(item);
    }

    // Keep only 50 items in the DOM
    while (eventsFeed.children.length > 50) {
      eventsFeed.removeChild(eventsFeed.lastChild);
    }
  }

  function createEventItem(evt) {
    var item = document.createElement('div');
    item.className = 'event-item';

    var evtType = (evt.event_type || 'system').toLowerCase();
    var typeClass = 'system';
    if (evtType.indexOf('trade') >= 0) typeClass = 'trade';
    else if (evtType.indexOf('error') >= 0) typeClass = 'error';
    else if (evtType.indexOf('signal') >= 0) typeClass = 'signal';

    item.innerHTML =
      '<span class="event-time">' + Utils.formatTime(evt.timestamp || evt.created_at) + '</span>' +
      '<span class="event-type ' + typeClass + '">' + escapeHtml(evtType) + '</span>' +
      '<span class="event-message">' + escapeHtml(evt.message || evt.data || '') + '</span>';

    return item;
  }

  // ---------------------------------------------------------------------------
  // Data Loading (REST API)
  // ---------------------------------------------------------------------------

  function loadInitialData() {
    // Load all initial data in parallel
    Promise.all([
      Utils.fetchJSON('/api/bots').catch(function () { return []; }),
      Utils.fetchJSON('/api/trades?limit=50').catch(function () { return []; }),
      Utils.fetchJSON('/api/trades/summary').catch(function () { return { bots: [], totals: {} }; }),
      Utils.fetchJSON('/api/positions').catch(function () { return []; }),
      Utils.fetchJSON('/api/events?limit=50').catch(function () { return []; })
    ]).then(function (results) {
      state.bots = results[0];
      state.trades = results[1];

      var summaryData = results[2];
      state.summary = {
        tradeCount: (summaryData.totals && summaryData.totals.trade_count) || 0,
        totalPnl: (summaryData.totals && summaryData.totals.total_pnl) || 0,
        winRate: (summaryData.totals && summaryData.totals.win_rate) || 0
      };

      state.positions = results[3];
      state.events = results[4];

      // Render everything
      BotCard.renderBotCards(botCardsContainer, state.bots);
      updateHeaderStats();
      renderPositions();
      renderEvents(state.events);
      loadEquityChart();
    });
  }

  function loadEquityChart() {
    Utils.fetchJSON('/api/pnl?interval=daily')
      .then(function (data) {
        var chartData = data.map(function (d) {
          return { time: d.period, value: d.cumulative_pnl || 0 };
        });
        Charts.createEquityCurve('equity-chart-container', chartData);
      })
      .catch(function () {
        // No data yet
      });
  }

  function refreshTrades() {
    Utils.fetchJSON('/api/trades?limit=50')
      .then(function (trades) {
        state.trades = trades;
        if (tradeTableContainer._tradeState) {
          TradeTable.updateTradeTable(tradeTableContainer, state.trades);
        }
      })
      .catch(function () {});
  }

  function refreshSummary() {
    Utils.fetchJSON('/api/trades/summary')
      .then(function (data) {
        state.summary = {
          tradeCount: (data.totals && data.totals.trade_count) || 0,
          totalPnl: (data.totals && data.totals.total_pnl) || 0,
          winRate: (data.totals && data.totals.win_rate) || 0
        };
        updateHeaderStats();
      })
      .catch(function () {});
  }

  function refreshPositions() {
    Utils.fetchJSON('/api/positions')
      .then(function (positions) {
        state.positions = positions;
        renderPositions();
      })
      .catch(function () {});
  }

  // ---------------------------------------------------------------------------
  // Periodic Fallback Polling (every 10 seconds)
  // ---------------------------------------------------------------------------
  setInterval(function () {
    refreshSummary();
    refreshPositions();

    // Refresh bots
    Utils.fetchJSON('/api/bots')
      .then(function (bots) {
        state.bots = bots;
        BotCard.renderBotCards(botCardsContainer, state.bots);
      })
      .catch(function () {});
  }, 10000);

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------------
  // Initialize
  // ---------------------------------------------------------------------------
  loadInitialData();

})();
