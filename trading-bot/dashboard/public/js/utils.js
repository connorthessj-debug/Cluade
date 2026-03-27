/* ==========================================================================
   Utility Functions
   ========================================================================== */

var Utils = (function () {
  'use strict';

  /**
   * Format a number as currency with color class.
   * Returns an HTML string: <span class="cell-positive">$1,234.56</span>
   */
  function formatCurrency(value, includeSpan) {
    if (includeSpan === undefined) includeSpan = true;
    var num = parseFloat(value) || 0;
    var sign = num >= 0 ? '+' : '';
    var formatted = sign + '$' + Math.abs(num).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    if (num < 0) formatted = '-$' + Math.abs(num).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    if (!includeSpan) return formatted;
    var cls = num >= 0 ? 'cell-positive' : 'cell-negative';
    return '<span class="' + cls + '">' + formatted + '</span>';
  }

  /**
   * Format a value as a plain currency string (no HTML).
   */
  function formatCurrencyPlain(value) {
    var num = parseFloat(value) || 0;
    var prefix = num >= 0 ? '+$' : '-$';
    return prefix + Math.abs(num).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  /**
   * Format as percentage.
   */
  function formatPercent(value) {
    var num = parseFloat(value) || 0;
    return num.toFixed(2) + '%';
  }

  /**
   * Relative time string (e.g., "5m ago", "2h ago").
   */
  function formatTime(timestamp) {
    if (!timestamp) return '--';
    var now = Date.now();
    var ts = typeof timestamp === 'number' ? timestamp : new Date(timestamp).getTime();
    if (isNaN(ts)) return '--';
    var diff = Math.floor((now - ts) / 1000);

    if (diff < 0) return 'just now';
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }

  /**
   * Full date/time string.
   */
  function formatDateTime(timestamp) {
    if (!timestamp) return '--';
    var d = new Date(timestamp);
    if (isNaN(d.getTime())) return '--';
    return d.toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false
    });
  }

  /**
   * DOM helper: create an element with optional class and text content.
   */
  function createElement(tag, className, content) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== undefined && content !== null) {
      if (typeof content === 'string' || typeof content === 'number') {
        el.textContent = String(content);
      }
    }
    return el;
  }

  /**
   * Returns an HTML string for a status badge.
   */
  function statusBadge(status) {
    var s = (status || 'unknown').toLowerCase();
    var cls = 'badge badge-stopped';
    if (s === 'running') cls = 'badge badge-running';
    else if (s === 'error') cls = 'badge badge-error';
    else if (s === 'warning') cls = 'badge badge-warning';
    return '<span class="' + cls + '">' + s + '</span>';
  }

  /**
   * Apply a brief flash animation to an element.
   */
  function flashElement(el) {
    el.classList.remove('flash-update');
    // Force reflow so re-adding the class restarts the animation
    void el.offsetWidth;
    el.classList.add('flash-update');
  }

  // ---------------------------------------------------------------------------
  // WebSocket connection helper with auto-reconnect
  // ---------------------------------------------------------------------------

  function createWebSocket(options) {
    var opts = options || {};
    var url = opts.url || ('ws://' + window.location.host);
    var onMessage = opts.onMessage || function () {};
    var onOpen = opts.onOpen || function () {};
    var onClose = opts.onClose || function () {};
    var reconnectDelay = opts.reconnectDelay || 3000;
    var maxReconnectDelay = opts.maxReconnectDelay || 30000;

    var ws = null;
    var currentDelay = reconnectDelay;
    var reconnectTimer = null;
    var intentionalClose = false;

    function connect() {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
      }

      try {
        ws = new WebSocket(url);
      } catch (e) {
        scheduleReconnect();
        return;
      }

      ws.onopen = function () {
        currentDelay = reconnectDelay;
        onOpen();
      };

      ws.onmessage = function (event) {
        try {
          var data = JSON.parse(event.data);
          onMessage(data);
        } catch (e) {
          console.warn('[WS] Failed to parse message:', e);
        }
      };

      ws.onclose = function () {
        onClose();
        if (!intentionalClose) {
          scheduleReconnect();
        }
      };

      ws.onerror = function () {
        // onclose will fire after onerror
      };
    }

    function scheduleReconnect() {
      if (reconnectTimer) return;
      reconnectTimer = setTimeout(function () {
        reconnectTimer = null;
        connect();
        // Exponential backoff
        currentDelay = Math.min(currentDelay * 1.5, maxReconnectDelay);
      }, currentDelay);
    }

    function close() {
      intentionalClose = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (ws) ws.close();
    }

    function send(data) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(typeof data === 'string' ? data : JSON.stringify(data));
      }
    }

    connect();

    return { close: close, send: send };
  }

  // ---------------------------------------------------------------------------
  // Simple HTTP fetch helpers
  // ---------------------------------------------------------------------------

  function fetchJSON(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    });
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    });
  }

  // Public API
  return {
    formatCurrency: formatCurrency,
    formatCurrencyPlain: formatCurrencyPlain,
    formatPercent: formatPercent,
    formatTime: formatTime,
    formatDateTime: formatDateTime,
    createElement: createElement,
    statusBadge: statusBadge,
    flashElement: flashElement,
    createWebSocket: createWebSocket,
    fetchJSON: fetchJSON,
    postJSON: postJSON
  };
})();
