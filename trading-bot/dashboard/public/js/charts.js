/* ==========================================================================
   Chart Utilities (TradingView lightweight-charts)
   ========================================================================== */

var Charts = (function () {
  'use strict';

  // Dark theme options matching the dashboard palette
  var darkTheme = {
    layout: {
      background: { type: 'solid', color: '#131722' },
      textColor: '#787b86',
      fontSize: 11
    },
    grid: {
      vertLines: { color: '#1e222d' },
      horzLines: { color: '#1e222d' }
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#2962ff', width: 1, style: 2, labelBackgroundColor: '#2962ff' },
      horzLine: { color: '#2962ff', width: 1, style: 2, labelBackgroundColor: '#2962ff' }
    },
    rightPriceScale: {
      borderColor: '#1e222d',
      scaleMargins: { top: 0.1, bottom: 0.1 }
    },
    timeScale: {
      borderColor: '#1e222d',
      timeVisible: true,
      secondsVisible: false
    }
  };

  // Store chart instances for cleanup / resize
  var chartInstances = {};

  /**
   * Create an equity curve (line chart) for cumulative P&L.
   * @param {string} containerId - DOM element id
   * @param {Array} data - [{time: 'YYYY-MM-DD', value: number}, ...]
   * @returns {object} { chart, series }
   */
  function createEquityCurve(containerId, data) {
    var container = document.getElementById(containerId);
    if (!container) return null;

    // Clear previous chart
    container.innerHTML = '';

    var chart = LightweightCharts.createChart(container, Object.assign({}, darkTheme, {
      width: container.clientWidth,
      height: container.clientHeight || 300
    }));

    var series = chart.addAreaSeries({
      lineColor: '#2962ff',
      topColor: 'rgba(41, 98, 255, 0.3)',
      bottomColor: 'rgba(41, 98, 255, 0.02)',
      lineWidth: 2,
      priceFormat: { type: 'custom', formatter: function (p) { return '$' + p.toFixed(2); } }
    });

    if (data && data.length) {
      series.setData(data);
      chart.timeScale().fitContent();
    }

    chartInstances[containerId] = { chart: chart, series: series };

    return { chart: chart, series: series };
  }

  /**
   * Create a candlestick / price chart.
   * @param {string} containerId
   * @param {Array} data - [{time, open, high, low, close}, ...]
   * @returns {object} { chart, series }
   */
  function createPriceChart(containerId, data) {
    var container = document.getElementById(containerId);
    if (!container) return null;

    container.innerHTML = '';

    var chart = LightweightCharts.createChart(container, Object.assign({}, darkTheme, {
      width: container.clientWidth,
      height: container.clientHeight || 400
    }));

    var series = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350'
    });

    if (data && data.length) {
      series.setData(data);
      chart.timeScale().fitContent();
    }

    chartInstances[containerId] = { chart: chart, series: series };

    return { chart: chart, series: series };
  }

  /**
   * Create a histogram (bar) chart for daily P&L.
   * @param {string} containerId
   * @param {Array} data - [{time, value, color}, ...]
   * @returns {object} { chart, series }
   */
  function createBarChart(containerId, data) {
    var container = document.getElementById(containerId);
    if (!container) return null;

    container.innerHTML = '';

    var chart = LightweightCharts.createChart(container, Object.assign({}, darkTheme, {
      width: container.clientWidth,
      height: container.clientHeight || 250
    }));

    var series = chart.addHistogramSeries({
      priceFormat: { type: 'custom', formatter: function (p) { return '$' + p.toFixed(2); } },
      priceScaleId: ''
    });

    if (data && data.length) {
      series.setData(data);
      chart.timeScale().fitContent();
    }

    chartInstances[containerId] = { chart: chart, series: series };

    return { chart: chart, series: series };
  }

  /**
   * Update a chart's series data.
   */
  function updateChart(containerId, newData) {
    var inst = chartInstances[containerId];
    if (!inst) return;
    inst.series.setData(newData);
    inst.chart.timeScale().fitContent();
  }

  /**
   * Append a single data point.
   */
  function appendPoint(containerId, point) {
    var inst = chartInstances[containerId];
    if (!inst) return;
    inst.series.update(point);
  }

  /**
   * Resize all charts (call on window resize).
   */
  function resizeAll() {
    Object.keys(chartInstances).forEach(function (id) {
      var container = document.getElementById(id);
      var inst = chartInstances[id];
      if (container && inst && inst.chart) {
        inst.chart.resize(container.clientWidth, container.clientHeight || 300);
      }
    });
  }

  /**
   * Destroy a chart instance.
   */
  function destroy(containerId) {
    var inst = chartInstances[containerId];
    if (inst && inst.chart) {
      inst.chart.remove();
      delete chartInstances[containerId];
    }
  }

  // Auto-resize on window resize
  var resizeTimeout;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(resizeAll, 150);
  });

  return {
    createEquityCurve: createEquityCurve,
    createPriceChart: createPriceChart,
    createBarChart: createBarChart,
    updateChart: updateChart,
    appendPoint: appendPoint,
    resizeAll: resizeAll,
    destroy: destroy,
    darkTheme: darkTheme
  };
})();
