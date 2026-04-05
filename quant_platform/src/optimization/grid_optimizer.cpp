#include "optimization/grid_optimizer.h"
#include "core/backtest_engine.h"
#include "metrics/metrics_engine.h"
#include "common/logger.h"
#include <cmath>

namespace qp {

ObjectiveFunction parseObjective(const std::string& name) {
    if (name == "sharpe")       return ObjectiveFunction::Sharpe;
    if (name == "sortino")      return ObjectiveFunction::Sortino;
    if (name == "totalReturn")  return ObjectiveFunction::TotalReturn;
    if (name == "profitFactor") return ObjectiveFunction::ProfitFactor;
    if (name == "expectancy")   return ObjectiveFunction::Expectancy;
    return ObjectiveFunction::Sharpe;
}

double scoreByObjective(const MetricsSummary& metrics, ObjectiveFunction obj) {
    switch (obj) {
        case ObjectiveFunction::Sharpe:       return metrics.sharpeRatio;
        case ObjectiveFunction::Sortino:      return metrics.sortinoRatio;
        case ObjectiveFunction::TotalReturn:  return metrics.totalReturn;
        case ObjectiveFunction::ProfitFactor: return metrics.profitFactor;
        case ObjectiveFunction::Expectancy:   return metrics.expectancy;
    }
    return metrics.sharpeRatio;
}

// Generate all combinations from param ranges
static void generateCombinations(
    const std::vector<ParamRange>& ranges,
    size_t depth,
    StrategyParams& current,
    std::vector<StrategyParams>& allCombinations)
{
    if (depth == ranges.size()) {
        allCombinations.push_back(current);
        return;
    }

    const auto& r = ranges[depth];
    for (double val = r.min; val <= r.max + r.step * 0.01; val += r.step) {
        current.params[r.name] = val;
        generateCombinations(ranges, depth + 1, current, allCombinations);
    }
}

OptimizationResult GridOptimizer::optimize(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const std::vector<ParamRange>& ranges,
    ObjectiveFunction objective,
    const AppConfig& config)
{
    Logger& log = Logger::instance();
    log.info("Starting grid optimization...");

    std::vector<StrategyParams> allCombinations;
    StrategyParams base;
    base.strategyName = strategy.name();
    generateCombinations(ranges, 0, base, allCombinations);

    OptimizationResult result;
    result.objectiveName = "grid";
    result.totalCombinations = static_cast<int>(allCombinations.size());

    log.info("Grid optimizer: " + std::to_string(allCombinations.size()) + " combinations");

    BacktestEngine engine;
    engine.configure(config);
    MetricsEngine metricsEngine(config);

    for (size_t i = 0; i < allCombinations.size(); i++) {
        strategy.reset();
        BacktestSnapshot snap = engine.run(bars, strategy, allCombinations[i]);
        MetricsSummary metrics = metricsEngine.compute(snap);
        double score = scoreByObjective(metrics, objective);

        result.evaluatedCount++;

        if (score > result.bestScore) {
            result.bestScore = score;
            result.bestParams = allCombinations[i];
            result.bestMetrics = metrics;
        }

        if ((i + 1) % 50 == 0) {
            log.info("  Evaluated " + std::to_string(i + 1) + "/" +
                     std::to_string(allCombinations.size()));
        }
    }

    log.info("Grid optimization complete. Best score: " + std::to_string(result.bestScore));
    return result;
}

} // namespace qp
