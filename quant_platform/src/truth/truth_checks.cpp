#include "truth/truth_checks.h"
#include "core/backtest_engine.h"
#include "metrics/metrics_engine.h"
#include "montecarlo/monte_carlo_engine.h"
#include "common/logger.h"
#include <cmath>
#include <algorithm>

namespace qp {

TruthCheckResult checkSlippageFragility(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& baseConfig,
    const std::vector<double>& multipliers)
{
    TruthCheckResult result;
    result.checkName = "slippage_fragility";

    BacktestEngine engine;
    MetricsEngine metricsEngine(baseConfig);

    // Baseline
    AppConfig baseCfg = baseConfig;
    engine.configure(baseCfg);
    strategy.reset();
    auto baseSnap = engine.run(bars, strategy, params);
    auto baseMetrics = metricsEngine.compute(baseSnap);
    double baseSharpe = baseMetrics.sharpeRatio;

    double worstDecay = 0.0;
    for (double mult : multipliers) {
        AppConfig cfg = baseConfig;
        cfg.costs.slippageFactor *= mult;
        engine.configure(cfg);
        strategy.reset();
        auto snap = engine.run(bars, strategy, params);
        auto metrics = metricsEngine.compute(snap);

        double decay = (std::abs(baseSharpe) > 0.001)
            ? (baseSharpe - metrics.sharpeRatio) / std::abs(baseSharpe)
            : 0.0;
        worstDecay = std::max(worstDecay, decay);
    }

    result.score = std::max(0.0, 1.0 - worstDecay);
    result.passed = (worstDecay < 0.5);
    result.detail = "Worst Sharpe decay under slippage stress: " + std::to_string(worstDecay * 100.0) + "%";
    return result;
}

TruthCheckResult checkSpreadShock(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& baseConfig,
    double spreadMultiplier)
{
    TruthCheckResult result;
    result.checkName = "spread_shock";

    BacktestEngine engine;
    MetricsEngine metricsEngine(baseConfig);

    engine.configure(baseConfig);
    strategy.reset();
    auto baseSnap = engine.run(bars, strategy, params);
    auto baseMetrics = metricsEngine.compute(baseSnap);

    AppConfig shockCfg = baseConfig;
    shockCfg.costs.spreadFactor *= spreadMultiplier;
    engine.configure(shockCfg);
    strategy.reset();
    auto shockSnap = engine.run(bars, strategy, params);
    auto shockMetrics = metricsEngine.compute(shockSnap);

    double decay = (std::abs(baseMetrics.sharpeRatio) > 0.001)
        ? (baseMetrics.sharpeRatio - shockMetrics.sharpeRatio) / std::abs(baseMetrics.sharpeRatio)
        : 0.0;

    result.score = std::max(0.0, 1.0 - decay);
    result.passed = (decay < 0.5);
    result.detail = "Sharpe decay under " + std::to_string(spreadMultiplier) + "x spread: " +
                    std::to_string(decay * 100.0) + "%";
    return result;
}

TruthCheckResult checkLatencyFragility(
    const BacktestSnapshot& baseSnapshot,
    const MetricsSummary& baseMetrics)
{
    TruthCheckResult result;
    result.checkName = "latency_fragility";
    // Approximate: if avg holding period is very short, latency is a risk
    double avgHoldBars = 0.0;
    if (!baseSnapshot.trades.empty()) {
        double sum = 0.0;
        for (const auto& t : baseSnapshot.trades) sum += t.holdingPeriod;
        avgHoldBars = sum / static_cast<double>(baseSnapshot.trades.size());
    }
    result.score = std::min(1.0, avgHoldBars / 5.0); // 5+ bars holding = low latency risk
    result.passed = (avgHoldBars >= 2.0);
    result.detail = "Avg holding period: " + std::to_string(avgHoldBars) + " bars";
    return result;
}

TruthCheckResult checkMissedTradeFragility(
    const std::vector<Trade>& trades,
    double initialCapital,
    double missedRate)
{
    TruthCheckResult result;
    result.checkName = "missed_trade_fragility";

    MonteCarloEngine mc;
    auto summary = mc.runMissedTrades(trades, initialCapital, 500, missedRate);

    result.score = std::max(0.0, 1.0 - summary.failureRate);
    result.passed = (summary.failureRate < 0.25);
    result.detail = "Failure rate with " + std::to_string(missedRate * 100.0) + "% missed trades: " +
                    std::to_string(summary.failureRate * 100.0) + "%";
    return result;
}

TruthCheckResult checkParameterStability(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& config,
    double perturbPct)
{
    TruthCheckResult result;
    result.checkName = "parameter_stability";

    BacktestEngine engine;
    engine.configure(config);
    MetricsEngine metricsEngine(config);

    strategy.reset();
    auto baseSnap = engine.run(bars, strategy, params);
    auto baseMetrics = metricsEngine.compute(baseSnap);
    double baseSharpe = baseMetrics.sharpeRatio;

    double maxDecay = 0.0;
    int perturbCount = 0;

    for (const auto& [key, val] : params.params) {
        for (double sign : {-1.0, 1.0}) {
            StrategyParams perturbed = params;
            perturbed.params[key] = val * (1.0 + sign * perturbPct);

            strategy.reset();
            auto snap = engine.run(bars, strategy, perturbed);
            auto metrics = metricsEngine.compute(snap);

            double decay = (std::abs(baseSharpe) > 0.001)
                ? std::abs(baseSharpe - metrics.sharpeRatio) / std::abs(baseSharpe)
                : 0.0;
            maxDecay = std::max(maxDecay, decay);
            perturbCount++;
        }
    }

    result.score = std::max(0.0, 1.0 - maxDecay);
    result.passed = (maxDecay < 0.4);
    result.detail = "Max Sharpe variance under " + std::to_string(perturbPct * 100.0) +
                    "% param perturbation: " + std::to_string(maxDecay * 100.0) + "%";
    return result;
}

TruthCheckResult checkWalkForwardConsistency(const WalkForwardReport& wfReport) {
    TruthCheckResult result;
    result.checkName = "walk_forward_consistency";
    result.score = wfReport.consistencyScore;
    result.passed = wfReport.passed;
    result.detail = "WF consistency=" + std::to_string(wfReport.consistencyScore) +
                    ", avgDegradation=" + std::to_string(wfReport.avgDegradation);
    return result;
}

TruthCheckResult checkMonteCarloRobustness(
    const MonteCarloSummary& mcSummary,
    double hardFailRate)
{
    TruthCheckResult result;
    result.checkName = "monte_carlo_robustness";
    result.score = std::max(0.0, 1.0 - mcSummary.failureRate);
    result.passed = (mcSummary.failureRate < hardFailRate);
    result.detail = "MC failure rate: " + std::to_string(mcSummary.failureRate * 100.0) +
                    "%, threshold: " + std::to_string(hardFailRate * 100.0) + "%";
    return result;
}

TruthCheckResult checkRegimeDependence(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& config,
    double splitRatio)
{
    TruthCheckResult result;
    result.checkName = "regime_dependence";

    int splitPoint = static_cast<int>(static_cast<double>(bars.size()) * splitRatio);
    if (splitPoint < 10 || splitPoint >= static_cast<int>(bars.size()) - 10) {
        result.score = 0.5;
        result.passed = true;
        result.detail = "Not enough data to split for regime analysis";
        return result;
    }

    std::vector<Bar> firstHalf(bars.begin(), bars.begin() + splitPoint);
    std::vector<Bar> secondHalf(bars.begin() + splitPoint, bars.end());
    for (size_t i = 0; i < firstHalf.size(); i++) firstHalf[i].index = static_cast<int64_t>(i);
    for (size_t i = 0; i < secondHalf.size(); i++) secondHalf[i].index = static_cast<int64_t>(i);

    BacktestEngine engine;
    engine.configure(config);
    MetricsEngine metricsEngine(config);

    strategy.reset();
    auto snap1 = engine.run(firstHalf, strategy, params);
    auto metrics1 = metricsEngine.compute(snap1);

    strategy.reset();
    auto snap2 = engine.run(secondHalf, strategy, params);
    auto metrics2 = metricsEngine.compute(snap2);

    double avgSharpe = (metrics1.sharpeRatio + metrics2.sharpeRatio) / 2.0;
    double sharpeDiff = std::abs(metrics1.sharpeRatio - metrics2.sharpeRatio);
    double relDiff = (std::abs(avgSharpe) > 0.001) ? sharpeDiff / std::abs(avgSharpe) : sharpeDiff;

    result.score = std::max(0.0, 1.0 - relDiff);
    result.passed = (relDiff < 0.8);
    result.detail = "First-half Sharpe=" + std::to_string(metrics1.sharpeRatio) +
                    ", Second-half Sharpe=" + std::to_string(metrics2.sharpeRatio) +
                    ", Relative diff=" + std::to_string(relDiff * 100.0) + "%";
    return result;
}

} // namespace qp
