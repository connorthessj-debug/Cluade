#pragma once

#include "common/data_models.h"
#include "strategy/strategy_interface.h"
#include <vector>

namespace qp {

TruthCheckResult checkSlippageFragility(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& baseConfig,
    const std::vector<double>& multipliers);

TruthCheckResult checkSpreadShock(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& baseConfig,
    double spreadMultiplier);

TruthCheckResult checkLatencyFragility(
    const BacktestSnapshot& baseSnapshot,
    const MetricsSummary& baseMetrics);

TruthCheckResult checkMissedTradeFragility(
    const std::vector<Trade>& trades,
    double initialCapital,
    double missedRate);

TruthCheckResult checkParameterStability(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& config,
    double perturbPct);

TruthCheckResult checkWalkForwardConsistency(
    const WalkForwardReport& wfReport);

TruthCheckResult checkMonteCarloRobustness(
    const MonteCarloSummary& mcSummary,
    double hardFailRate);

TruthCheckResult checkRegimeDependence(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& config,
    double splitRatio);

} // namespace qp
