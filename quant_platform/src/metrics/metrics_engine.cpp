#include "metrics/metrics_engine.h"
#include "metrics/metric_utils.h"
#include <cmath>
#include <algorithm>

namespace qp {

MetricsEngine::MetricsEngine(const AppConfig& config)
    : m_riskFreeRate(config.riskFreeRate)
    , m_tradingDaysPerYear(config.tradingDaysPerYear)
{}

MetricsSummary MetricsEngine::compute(const BacktestSnapshot& snapshot) const {
    MetricsSummary m;

    if (snapshot.initialCapital <= 0.0) return m;

    // Total return
    m.totalReturn = (snapshot.finalEquity - snapshot.initialCapital) / snapshot.initialCapital;

    // CAGR
    int numBars = static_cast<int>(snapshot.equityCurve.size());
    double years = static_cast<double>(numBars) / static_cast<double>(m_tradingDaysPerYear);
    if (years > 0.0 && snapshot.finalEquity > 0.0) {
        m.cagr = std::pow(snapshot.finalEquity / snapshot.initialCapital, 1.0 / years) - 1.0;
    }

    // Daily returns
    auto returns = dailyReturns(snapshot.equityCurve);

    // Sharpe ratio
    if (!returns.empty()) {
        double avgReturn = mean(returns);
        double stdDev = standardDeviation(returns);
        double dailyRF = m_riskFreeRate / static_cast<double>(m_tradingDaysPerYear);
        if (stdDev > 0.0) {
            m.sharpeRatio = (avgReturn - dailyRF) / stdDev * std::sqrt(static_cast<double>(m_tradingDaysPerYear));
        }
    }

    // Sortino ratio
    if (!returns.empty()) {
        double avgReturn = mean(returns);
        double dailyRF = m_riskFreeRate / static_cast<double>(m_tradingDaysPerYear);
        double dd = downsideDeviation(returns, dailyRF);
        if (dd > 0.0) {
            m.sortinoRatio = (avgReturn - dailyRF) / dd * std::sqrt(static_cast<double>(m_tradingDaysPerYear));
        }
    }

    // Max drawdown
    auto ddInfo = maxDrawdown(snapshot.equityCurve);
    m.maxDrawdown = ddInfo.maxDrawdown;
    m.maxDrawdownDuration = ddInfo.maxDDDuration;

    // Trade-level metrics
    m.totalTrades = static_cast<int>(snapshot.trades.size());
    double grossProfit = 0.0;
    double grossLoss = 0.0;
    int wins = 0;

    for (const auto& trade : snapshot.trades) {
        if (trade.pnl > 0.0) {
            grossProfit += trade.pnl;
            wins++;
        } else {
            grossLoss += std::abs(trade.pnl);
        }
    }

    m.winningTrades = wins;
    m.losingTrades = m.totalTrades - wins;
    m.grossProfit = grossProfit;
    m.grossLoss = grossLoss;

    if (m.totalTrades > 0) {
        m.winRate = static_cast<double>(wins) / static_cast<double>(m.totalTrades);
        double totalPnl = grossProfit - grossLoss;
        m.avgTrade = totalPnl / static_cast<double>(m.totalTrades);
    }

    // Profit factor
    if (grossLoss > 0.0) {
        m.profitFactor = grossProfit / grossLoss;
    } else if (grossProfit > 0.0) {
        m.profitFactor = 999.0;
    }

    // Expectancy
    if (m.totalTrades > 0) {
        double avgWin = (wins > 0) ? grossProfit / static_cast<double>(wins) : 0.0;
        double avgLoss = (m.losingTrades > 0) ? grossLoss / static_cast<double>(m.losingTrades) : 0.0;
        m.expectancy = m.winRate * avgWin - (1.0 - m.winRate) * avgLoss;
    }

    return m;
}

} // namespace qp
