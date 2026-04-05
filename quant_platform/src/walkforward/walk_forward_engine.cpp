#include "walkforward/walk_forward_engine.h"
#include "optimization/grid_optimizer.h"
#include "core/backtest_engine.h"
#include "metrics/metrics_engine.h"
#include "common/logger.h"
#include "common/json.hpp"
#include <fstream>
#include <cmath>
#include <algorithm>

namespace qp {

WalkForwardConfig loadWalkForwardConfig(const std::string& path) {
    WalkForwardConfig config;
    std::ifstream file(path);
    if (!file.is_open()) {
        Logger::instance().warn("WF config not found: " + path + " — using defaults");
        return config;
    }

    nlohmann::json j;
    try {
        file >> j;
    } catch (...) {
        Logger::instance().error("Failed to parse WF config: " + path);
        return config;
    }

    if (j.contains("windowType"))    config.windowType    = j["windowType"].get<std::string>();
    if (j.contains("numWindows"))    config.numWindows    = j["numWindows"].get<int>();
    if (j.contains("inSampleRatio")) config.inSampleRatio = j["inSampleRatio"].get<double>();
    if (j.contains("objective"))     config.objective     = j["objective"].get<std::string>();

    return config;
}

WalkForwardReport WalkForwardEngine::run(
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const std::vector<ParamRange>& ranges,
    const WalkForwardConfig& wfConfig,
    const AppConfig& appConfig)
{
    Logger& log = Logger::instance();
    log.info("Starting walk-forward analysis: " + wfConfig.windowType +
             ", " + std::to_string(wfConfig.numWindows) + " windows");

    WalkForwardReport report;
    report.windowType = wfConfig.windowType;
    report.numWindows = wfConfig.numWindows;
    report.inSampleRatio = wfConfig.inSampleRatio;

    int totalBars = static_cast<int>(bars.size());
    if (totalBars < wfConfig.numWindows * 2) {
        log.error("Not enough bars for walk-forward analysis");
        return report;
    }

    ObjectiveFunction objective = parseObjective(wfConfig.objective);
    GridOptimizer optimizer;
    BacktestEngine btEngine;
    btEngine.configure(appConfig);
    MetricsEngine metricsEngine(appConfig);

    bool isRolling = (wfConfig.windowType == "rolling");
    int windowSize = totalBars / wfConfig.numWindows;
    double degradationSum = 0.0;

    for (int w = 0; w < wfConfig.numWindows; w++) {
        WalkForwardWindowResult wResult;
        wResult.windowIndex = w;

        int windowStart, windowEnd;
        if (isRolling) {
            windowStart = w * windowSize;
            windowEnd = std::min(windowStart + windowSize, totalBars);
        } else {
            // Anchored: IS always starts from 0
            windowStart = 0;
            windowEnd = std::min((w + 1) * windowSize, totalBars);
        }

        int isSize = static_cast<int>(static_cast<double>(windowEnd - windowStart) * wfConfig.inSampleRatio);
        int isStart = windowStart;
        int isEnd = windowStart + isSize;
        int oosStart = isEnd;
        int oosEnd = windowEnd;

        if (oosStart >= oosEnd || isStart >= isEnd) continue;

        wResult.isStartBar = isStart;
        wResult.isEndBar = isEnd;
        wResult.oosStartBar = oosStart;
        wResult.oosEndBar = oosEnd;

        // Extract in-sample bars
        std::vector<Bar> isBars(bars.begin() + isStart, bars.begin() + isEnd);
        // Re-index
        for (size_t i = 0; i < isBars.size(); i++) isBars[i].index = static_cast<int64_t>(i);

        // Optimize on in-sample
        strategy.reset();
        OptimizationResult optResult = optimizer.optimize(isBars, strategy, ranges, objective, appConfig);
        wResult.bestParams = optResult.bestParams;
        wResult.inSampleMetrics = optResult.bestMetrics;

        // Run out-of-sample with best params
        std::vector<Bar> oosBars(bars.begin() + oosStart, bars.begin() + oosEnd);
        for (size_t i = 0; i < oosBars.size(); i++) oosBars[i].index = static_cast<int64_t>(i);

        strategy.reset();
        BacktestSnapshot oosSnap = btEngine.run(oosBars, strategy, optResult.bestParams);
        wResult.outOfSampleMetrics = metricsEngine.compute(oosSnap);

        // Degradation ratio
        if (std::abs(wResult.inSampleMetrics.sharpeRatio) > 0.001) {
            wResult.degradationRatio = wResult.outOfSampleMetrics.sharpeRatio /
                                       wResult.inSampleMetrics.sharpeRatio;
        }
        degradationSum += wResult.degradationRatio;

        report.windows.push_back(wResult);
        log.info("  Window " + std::to_string(w) + ": IS Sharpe=" +
                 std::to_string(wResult.inSampleMetrics.sharpeRatio) +
                 ", OOS Sharpe=" + std::to_string(wResult.outOfSampleMetrics.sharpeRatio) +
                 ", Degradation=" + std::to_string(wResult.degradationRatio));
    }

    if (!report.windows.empty()) {
        report.avgDegradation = degradationSum / static_cast<double>(report.windows.size());
    }

    // Consistency: fraction of windows with positive OOS Sharpe
    int positiveOOS = 0;
    for (const auto& w : report.windows) {
        if (w.outOfSampleMetrics.sharpeRatio > 0.0) positiveOOS++;
    }
    report.consistencyScore = report.windows.empty() ? 0.0 :
        static_cast<double>(positiveOOS) / static_cast<double>(report.windows.size());
    report.passed = (report.consistencyScore >= 0.5 && report.avgDegradation >= 0.3);

    log.info("Walk-forward complete: avgDegradation=" + std::to_string(report.avgDegradation) +
             ", consistency=" + std::to_string(report.consistencyScore) +
             ", passed=" + std::string(report.passed ? "true" : "false"));

    return report;
}

} // namespace qp
