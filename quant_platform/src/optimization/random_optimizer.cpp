#include "optimization/random_optimizer.h"
#include "core/backtest_engine.h"
#include "metrics/metrics_engine.h"
#include "common/logger.h"
#include <random>
#include <cmath>

namespace qp {

RandomOptimizer::RandomOptimizer(int maxIterations, unsigned int seed)
    : m_maxIterations(maxIterations)
    , m_seed(seed)
{}

OptimizationResult RandomOptimizer::optimize(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const std::vector<ParamRange>& ranges,
    ObjectiveFunction objective,
    const AppConfig& config)
{
    Logger& log = Logger::instance();
    log.info("Starting random optimization (" + std::to_string(m_maxIterations) + " iterations)...");

    std::mt19937 rng(m_seed == 0 ? std::random_device{}() : m_seed);

    OptimizationResult result;
    result.objectiveName = "random";
    result.totalCombinations = m_maxIterations;

    BacktestEngine engine;
    engine.configure(config);
    MetricsEngine metricsEngine(config);

    for (int i = 0; i < m_maxIterations; i++) {
        StrategyParams params;
        params.strategyName = strategy.name();

        // Sample random parameters within ranges, snapped to step
        for (const auto& r : ranges) {
            std::uniform_real_distribution<double> dist(r.min, r.max);
            double val = dist(rng);
            if (r.step > 0.0) {
                val = r.min + std::round((val - r.min) / r.step) * r.step;
                val = std::min(val, r.max);
            }
            params.params[r.name] = val;
        }

        strategy.reset();
        BacktestSnapshot snap = engine.run(bars, strategy, params);
        MetricsSummary metrics = metricsEngine.compute(snap);
        double score = scoreByObjective(metrics, objective);

        result.evaluatedCount++;

        if (score > result.bestScore) {
            result.bestScore = score;
            result.bestParams = params;
            result.bestMetrics = metrics;
        }

        if ((i + 1) % 100 == 0) {
            log.info("  Random optimizer: " + std::to_string(i + 1) + "/" +
                     std::to_string(m_maxIterations));
        }
    }

    log.info("Random optimization complete. Best score: " + std::to_string(result.bestScore));
    return result;
}

} // namespace qp
