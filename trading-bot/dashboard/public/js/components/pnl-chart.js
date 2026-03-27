/* ==========================================================================
   P&L Chart Component (Analytics Tab)
   ========================================================================== */

var PnlChart = (function () {
  'use strict';

  var initialized = false;

  /**
   * Initialize the analytics / P&L chart section.
   * @param {HTMLElement} container - #pnl-chart-container
   */
  function init(container) {
    container.innerHTML = '';

    // Build the analytics layout
    var html =
      '<div class="analytics-grid">' +
        // Cumulative P&L
        '<div class="card">' +
          '<div class="card-header">' +
            '<h3>Cumulative P&L</h3>' +
            '<div class="chart-controls" id="cum-pnl-controls"></div>' +
          '</div>' +
          '<div id="cum-pnl-chart" class="chart-container" style="height:320px"></div>' +
        '</div>' +
        // Daily P&L bars
        '<div class="card">' +
          '<div class="card-header"><h3>Daily P&L</h3></div>' +
          '<div id="daily-pnl-chart" class="chart-container" style="height:250px"></div>' +
        '</div>' +
        // Drawdown
        '<div class="card">' +
          '<div class="card-header"><h3>Drawdown</h3></div>' +
          '<div id="drawdown-chart" class="chart-container" style="height:200px"></div>' +
        '</div>' +
      '</div>';

    container.innerHTML = html;
    initialized = true;
  }

  /**
   * Load P&L data and render all charts.
   * @param {HTMLElement} container
   * @param {string} [bot] - Optional bot filter
   */
  function load(container, bot) {
    if (!initialized) init(container);

    var url = '/api/pnl?interval=daily';
    if (bot) url += '&bot=' + encodeURIComponent(bot);

    Utils.fetchJSON(url)
      .then(function (data) {
        renderCumulativePnl(data);
        renderDailyPnl(data);
        renderDrawdown(data);
      })
      .catch(function (err) {
        console.error('[PnlChart] Failed to load:', err);
      });
  }

  /**
   * Render the cumulative P&L line chart.
   */
  function renderCumulativePnl(data) {
    var chartData = data.map(function (d) {
      return { time: d.period, value: d.cumulative_pnl || 0 };
    });
    Charts.createEquityCurve('cum-pnl-chart', chartData);
  }

  /**
   * Render the daily P&L bar chart.
   */
  function renderDailyPnl(data) {
    var chartData = data.map(function (d) {
      var pnl = d.pnl || 0;
      return {
        time: d.period,
        value: pnl,
        color: pnl >= 0 ? '#26a69a' : '#ef5350'
      };
    });
    Charts.createBarChart('daily-pnl-chart', chartData);
  }

  /**
   * Render the drawdown chart.
   */
  function renderDrawdown(data) {
    var peak = 0;
    var chartData = data.map(function (d) {
      var cum = d.cumulative_pnl || 0;
      if (cum > peak) peak = cum;
      var dd = peak > 0 ? ((cum - peak) / peak) * 100 : 0;
      if (peak === 0 && cum < 0) dd = -100;
      return { time: d.period, value: dd };
    });

    var container = document.getElementById('drawdown-chart');
    if (!container) return;
    container.innerHTML = '';

    var chart = LightweightCharts.createChart(container, Object.assign({}, Charts.darkTheme, {
      width: container.clientWidth,
      height: container.clientHeight || 200
    }));

    var series = chart.addAreaSeries({
      lineColor: '#ef5350',
      topColor: 'rgba(239, 83, 80, 0.02)',
      bottomColor: 'rgba(239, 83, 80, 0.2)',
      lineWidth: 1,
      priceFormat: { type: 'custom', formatter: function (p) { return p.toFixed(2) + '%'; } }
    });

    if (chartData.length) {
      series.setData(chartData);
      chart.timeScale().fitContent();
    }
  }

  /**
   * Update charts with fresh data (called on WS updates).
   */
  function refresh(container) {
    load(container);
  }

  return {
    init: init,
    load: load,
    refresh: refresh
  };
})();
