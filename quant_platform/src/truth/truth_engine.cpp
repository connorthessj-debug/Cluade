#include "truth/truth_engine.h"
#include "truth/truth_checks.h"
#include "montecarlo/monte_carlo_engine.h"
#include "common/logger.h"
#include "common/json.hpp"
#include <fstream>
#include <numeric>

namespace qp {

void TruthEngine::loadConfig(const std::string& configPath) {
    std::ifstream file(configPath);
    if (!file.is_open()) {
        Logger::instance().warn("Truth config not found: " + configPath + " — using defaults");
        return;
    }

    nlohmann::json j;
    try {
        file >> j;
    } catch (...) {
        Logger::instance().error("Failed to parse truth config");
        return;
    }

    if (j.contains("slippageMultipliers")) {
        m_slippageMultipliers.clear();
        for (auto& v : j["slippageMultipliers"]) {
            m_slippageMultipliers.push_back(v.get<double>());
        }
    }
    if (j.contains("spreadShockMultiplier"))    m_spreadShockMultiplier    = j["spreadShockMultiplier"].get<double>();
    if (j.contains("paramPerturbPct"))          m_paramPerturbPct          = j["paramPerturbPct"].get<double>();
    if (j.contains("missedTradeRate"))          m_missedTradeRate          = j["missedTradeRate"].get<double>();
    if (j.contains("hardFailMaxDrawdown"))      m_hardFailMaxDrawdown      = j["hardFailMaxDrawdown"].get<double>();
    if (j.contains("hardFailMCFailureRate"))    m_hardFailMCFailureRate    = j["hardFailMCFailureRate"].get<double>();
    if (j.contains("hardFailDegradationRatio")) m_hardFailDegradationRatio = j["hardFailDegradationRatio"].get<double>();
    if (j.contains("minSharpeForLive"))         m_minSharpeForLive         = j["minSharpeForLive"].get<double>();
    if (j.contains("minWinRateForLive"))        m_minWinRateForLive        = j["minWinRateForLive"].get<double>();
    if (j.contains("regimeSplitRatio"))         m_regimeSplitRatio         = j["regimeSplitRatio"].get<double>();

    Logger::instance().info("Truth engine config loaded");
}

TruthReport TruthEngine::evaluate(
    const BacktestSnapshot& snapshot,
    const MetricsSummary& metrics,
    const std::vector<Bar>& bars,
    IStrategy& strategy,
    const StrategyParams& params,
    const AppConfig& appConfig)
{
    Logger& log = Logger::instance();
    log.info("Running Truth Engine evaluation...");

    TruthReport report;

    // 1. Slippage fragility
    auto slippageCheck = checkSlippageFragility(bars, strategy, params, appConfig, m_slippageMultipliers);
    report.checks.push_back(slippageCheck);
    report.executionFragility = 1.0 - slippageCheck.score;

    // 2. Spread shock
    auto spreadCheck = checkSpreadShock(bars, strategy, params, appConfig, m_spreadShockMultiplier);
    report.checks.push_back(spreadCheck);
    report.costSensitivity = 1.0 - spreadCheck.score;

    // 3. Latency
    auto latencyCheck = checkLatencyFragility(snapshot, metrics);
    report.checks.push_back(latencyCheck);

    // 4. Missed trade
    auto missedCheck = checkMissedTradeFragility(snapshot.trades, appConfig.initialCapital, m_missedTradeRate);
    report.checks.push_back(missedCheck);

    // 5. Parameter stability
    auto paramCheck = checkParameterStability(bars, strategy, params, appConfig, m_paramPerturbPct);
    report.checks.push_back(paramCheck);
    report.overfitRisk = 1.0 - paramCheck.score;

    // 6. Monte Carlo robustness
    MonteCarloEngine mc;
    auto mcSummary = mc.run(snapshot.trades, appConfig.initialCapital, 500);
    auto mcCheck = checkMonteCarloRobustness(mcSummary, m_hardFailMCFailureRate);
    report.checks.push_back(mcCheck);
    report.robustnessScore = mcCheck.score;

    // 7. Regime dependence
    auto regimeCheck = checkRegimeDependence(bars, strategy, params, appConfig, m_regimeSplitRatio);
    report.checks.push_back(regimeCheck);
    report.regimeDependence = 1.0 - regimeCheck.score;

    // Compute overall score (average of all check scores)
    double totalScore = 0.0;
    for (const auto& c : report.checks) totalScore += c.score;
    report.overallScore = report.checks.empty() ? 0.0 :
        totalScore / static_cast<double>(report.checks.size());

    // Apply hard-fail rules
    applyHardFailRules(report, metrics);

    // Recommended actions
    for (const auto& c : report.checks) {
        if (!c.passed) {
            report.recommendedActions.push_back("Address: " + c.checkName + " — " + c.detail);
        }
    }

    log.info("Truth Engine complete. Overall score: " + std::to_string(report.overallScore));
    return report;
}

void TruthEngine::applyHardFailRules(TruthReport& report, const MetricsSummary& metrics) {
    report.passForPaperTrading = true;
    report.passForLiveCapital = true;

    // Hard fail: max drawdown
    if (metrics.maxDrawdown > m_hardFailMaxDrawdown) {
        report.criticalFailures.push_back("Max drawdown " +
            std::to_string(metrics.maxDrawdown * 100.0) + "% exceeds " +
            std::to_string(m_hardFailMaxDrawdown * 100.0) + "% limit");
        report.passForLiveCapital = false;
    }

    // Hard fail: MC failure rate
    for (const auto& c : report.checks) {
        if (c.checkName == "monte_carlo_robustness" && !c.passed) {
            report.criticalFailures.push_back("Monte Carlo failure rate too high");
            report.passForLiveCapital = false;
        }
    }

    // Sharpe too low for live
    if (metrics.sharpeRatio < m_minSharpeForLive) {
        report.criticalFailures.push_back("Sharpe ratio " +
            std::to_string(metrics.sharpeRatio) + " below live threshold " +
            std::to_string(m_minSharpeForLive));
        report.passForLiveCapital = false;
    }

    // Win rate too low
    if (metrics.winRate < m_minWinRateForLive) {
        report.criticalFailures.push_back("Win rate " +
            std::to_string(metrics.winRate * 100.0) + "% below threshold " +
            std::to_string(m_minWinRateForLive * 100.0) + "%");
        report.passForPaperTrading = false;
        report.passForLiveCapital = false;
    }

    // If any critical failure, override average score for live
    if (!report.criticalFailures.empty()) {
        report.passForLiveCapital = false;
    }
}

} // namespace qp
