#include "io/report_writer.h"
#include "common/logger.h"
#include <fstream>
#include <iomanip>
#include <sstream>

namespace qp {

void ReportWriter::writeMetricsReport(const std::string& path, const MetricsSummary& m) {
    std::ofstream f(path);
    if (!f.is_open()) {
        Logger::instance().error("Cannot write metrics report to: " + path);
        return;
    }

    f << std::fixed << std::setprecision(4);
    f << "===== Metrics Report =====\n";
    f << "Total Return:      " << (m.totalReturn * 100.0) << "%\n";
    f << "CAGR:              " << (m.cagr * 100.0) << "%\n";
    f << "Sharpe Ratio:      " << m.sharpeRatio << "\n";
    f << "Sortino Ratio:     " << m.sortinoRatio << "\n";
    f << "Max Drawdown:      " << (m.maxDrawdown * 100.0) << "%\n";
    f << "DD Duration:       " << m.maxDrawdownDuration << " bars\n";
    f << "Expectancy:        " << m.expectancy << "\n";
    f << "Profit Factor:     " << m.profitFactor << "\n";
    f << "Win Rate:          " << (m.winRate * 100.0) << "%\n";
    f << "Avg Trade:         " << m.avgTrade << "\n";
    f << "Total Trades:      " << m.totalTrades << "\n";
    f << "Winning Trades:    " << m.winningTrades << "\n";
    f << "Losing Trades:     " << m.losingTrades << "\n";
    f << "Gross Profit:      " << m.grossProfit << "\n";
    f << "Gross Loss:        " << m.grossLoss << "\n";
    f << "==========================\n";

    Logger::instance().info("Metrics report written to: " + path);
}

void ReportWriter::writeTruthReport(const std::string& path, const TruthReport& tr) {
    std::ofstream f(path);
    if (!f.is_open()) {
        Logger::instance().error("Cannot write truth report to: " + path);
        return;
    }

    f << std::fixed << std::setprecision(3);
    f << "===== Truth Report =====\n";
    f << "Overall Score:       " << tr.overallScore << "\n";
    f << "Robustness:          " << tr.robustnessScore << "\n";
    f << "Overfit Risk:        " << tr.overfitRisk << "\n";
    f << "Exec Fragility:      " << tr.executionFragility << "\n";
    f << "Cost Sensitivity:    " << tr.costSensitivity << "\n";
    f << "Regime Dependence:   " << tr.regimeDependence << "\n";
    f << "Paper Trading:       " << (tr.passForPaperTrading ? "PASS" : "FAIL") << "\n";
    f << "Live Capital:        " << (tr.passForLiveCapital ? "PASS" : "FAIL") << "\n";

    f << "\nChecks:\n";
    for (auto& c : tr.checks) {
        f << "  [" << (c.passed ? "PASS" : "FAIL") << "] "
          << c.checkName << " (score=" << c.score << ") " << c.detail << "\n";
    }

    if (!tr.criticalFailures.empty()) {
        f << "\nCritical Failures:\n";
        for (auto& cf : tr.criticalFailures) f << "  - " << cf << "\n";
    }
    if (!tr.recommendedActions.empty()) {
        f << "\nRecommended Actions:\n";
        for (auto& a : tr.recommendedActions) f << "  - " << a << "\n";
    }
    f << "========================\n";

    Logger::instance().info("Truth report written to: " + path);
}

void ReportWriter::writeFullReport(const std::string& path,
                                    const BacktestSnapshot& snapshot,
                                    const MetricsSummary& metrics,
                                    const TruthReport& truth) {
    std::ofstream f(path);
    if (!f.is_open()) {
        Logger::instance().error("Cannot write full report to: " + path);
        return;
    }

    f << std::fixed << std::setprecision(4);
    f << "===== Full Platform Report =====\n\n";
    f << "Strategy: " << snapshot.strategyName << "\n";
    f << "Initial Capital: $" << snapshot.initialCapital << "\n";
    f << "Final Equity: $" << snapshot.finalEquity << "\n";
    f << "Total Commission: $" << snapshot.totalCommission << "\n";
    f << "Total Slippage: $" << snapshot.totalSlippage << "\n\n";

    f << "--- Metrics ---\n";
    f << "Total Return: " << (metrics.totalReturn * 100.0) << "%\n";
    f << "CAGR: " << (metrics.cagr * 100.0) << "%\n";
    f << "Sharpe: " << metrics.sharpeRatio << "\n";
    f << "Sortino: " << metrics.sortinoRatio << "\n";
    f << "Max DD: " << (metrics.maxDrawdown * 100.0) << "%\n";
    f << "Trades: " << metrics.totalTrades << "\n";
    f << "Win Rate: " << (metrics.winRate * 100.0) << "%\n\n";

    f << "--- Truth ---\n";
    f << "Overall: " << truth.overallScore << "\n";
    f << "Paper: " << (truth.passForPaperTrading ? "PASS" : "FAIL") << "\n";
    f << "Live: " << (truth.passForLiveCapital ? "PASS" : "FAIL") << "\n";
    f << "================================\n";

    Logger::instance().info("Full report written to: " + path);
}

} // namespace qp
