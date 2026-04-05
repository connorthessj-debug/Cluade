#include "common/logger.h"
#include "common/config_loader.h"
#include "common/data_models.h"
#include "io/csv_reader.h"
#include "core/backtest_engine.h"
#include "strategy/momentum_strategy.h"
#include "strategy/mean_reversion_strategy.h"
#include "metrics/metrics_engine.h"
#include "montecarlo/monte_carlo_engine.h"
#include "optimization/grid_optimizer.h"
#include "optimization/random_optimizer.h"
#include "walkforward/walk_forward_engine.h"
#include "truth/truth_engine.h"
#include "execution/execution_engine.h"

#include <iostream>
#include <string>
#include <memory>
#include <cstring>

#ifdef _WIN32
#include "gui/main_window.h"
#endif

static void printMetrics(const qp::MetricsSummary& m) {
    std::cout << "\n===== Metrics Summary =====\n";
    std::cout << "Total Return:     " << (m.totalReturn * 100.0) << "%\n";
    std::cout << "CAGR:             " << (m.cagr * 100.0) << "%\n";
    std::cout << "Sharpe Ratio:     " << m.sharpeRatio << "\n";
    std::cout << "Sortino Ratio:    " << m.sortinoRatio << "\n";
    std::cout << "Max Drawdown:     " << (m.maxDrawdown * 100.0) << "%\n";
    std::cout << "DD Duration:      " << m.maxDrawdownDuration << " bars\n";
    std::cout << "Expectancy:       " << m.expectancy << "\n";
    std::cout << "Profit Factor:    " << m.profitFactor << "\n";
    std::cout << "Win Rate:         " << (m.winRate * 100.0) << "%\n";
    std::cout << "Avg Trade:        " << m.avgTrade << "\n";
    std::cout << "Total Trades:     " << m.totalTrades << "\n";
    std::cout << "===========================\n";
}

static void printTruthReport(const qp::TruthReport& tr) {
    std::cout << "\n===== Truth Report =====\n";
    std::cout << "Overall Score:       " << tr.overallScore << "\n";
    std::cout << "Robustness:          " << tr.robustnessScore << "\n";
    std::cout << "Overfit Risk:        " << tr.overfitRisk << "\n";
    std::cout << "Exec Fragility:      " << tr.executionFragility << "\n";
    std::cout << "Cost Sensitivity:    " << tr.costSensitivity << "\n";
    std::cout << "Regime Dependence:   " << tr.regimeDependence << "\n";
    std::cout << "Paper Trading:       " << (tr.passForPaperTrading ? "PASS" : "FAIL") << "\n";
    std::cout << "Live Capital:        " << (tr.passForLiveCapital ? "PASS" : "FAIL") << "\n";
    if (!tr.criticalFailures.empty()) {
        std::cout << "Critical Failures:\n";
        for (auto& f : tr.criticalFailures) {
            std::cout << "  - " << f << "\n";
        }
    }
    if (!tr.recommendedActions.empty()) {
        std::cout << "Recommended Actions:\n";
        for (auto& a : tr.recommendedActions) {
            std::cout << "  - " << a << "\n";
        }
    }
    std::cout << "========================\n";
}

static bool hasFlag(int argc, char* argv[], const char* flag) {
    for (int i = 1; i < argc; i++) {
        if (std::strcmp(argv[i], flag) == 0) return true;
    }
    return false;
}

#ifdef _WIN32
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR lpCmdLine, int nCmdShow) {
    // Check for --console flag
    if (lpCmdLine && std::string(lpCmdLine).find("--console") != std::string::npos) {
        // Allocate console for output
        AllocConsole();
        freopen("CONOUT$", "w", stdout);
        freopen("CONOUT$", "w", stderr);
#else
int main(int argc, char* argv[]) {
    bool consoleMode = true;
    {
#endif
        qp::Logger& log = qp::Logger::instance();
        log.info("Quant Platform starting in console mode...");

        std::string configPath = "config/app_config.json";
        qp::AppConfig config = qp::loadAppConfig(configPath);
        log.setLevel(config.logLevel);

        // Load data
        std::vector<qp::Bar> bars = qp::loadBarsFromCSV(config.dataPath);
        if (bars.empty()) {
            log.error("No bar data loaded. Exiting.");
            return 1;
        }

        // Create strategy
        std::unique_ptr<qp::IStrategy> strategy;
        qp::StrategyParams params;

        if (config.defaultStrategy == "momentum") {
            strategy = std::make_unique<qp::MomentumStrategy>();
            params.strategyName = "momentum";
            params.params["lookbackPeriod"] = 10;
            params.params["entryThreshold"] = 0.02;
            params.params["exitThreshold"] = -0.01;
            params.params["positionSize"] = 0.10;
        } else {
            strategy = std::make_unique<qp::MeanReversionStrategy>();
            params.strategyName = "mean_reversion";
            params.params["period"] = 20;
            params.params["stdDevMultiplier"] = 2.0;
            params.params["positionSize"] = 0.10;
        }

        // Run backtest
        qp::BacktestEngine engine;
        engine.configure(config);
        qp::BacktestSnapshot snapshot = engine.run(bars, *strategy, params);

        log.info("Backtest complete: " + std::to_string(snapshot.trades.size()) +
                 " trades, final equity: $" + std::to_string(snapshot.finalEquity));

        // Compute metrics
        qp::MetricsEngine metricsEngine(config);
        qp::MetricsSummary metrics = metricsEngine.compute(snapshot);
        printMetrics(metrics);

        // Monte Carlo
        qp::MonteCarloEngine mcEngine;
        qp::MonteCarloSummary mcSummary = mcEngine.run(snapshot.trades,
            config.initialCapital, config.monteCarloSims);
        log.info("Monte Carlo complete: median equity = $" +
                 std::to_string(mcSummary.medianFinalEquity) +
                 ", failure rate = " + std::to_string(mcSummary.failureRate * 100.0) + "%");

        // Truth Engine
        qp::TruthEngine truthEngine;
        truthEngine.loadConfig("config/truth_engine_config.json");
        qp::TruthReport truthReport = truthEngine.evaluate(
            snapshot, metrics, bars, *strategy, params, config);
        printTruthReport(truthReport);

        log.info("Console run complete.");
        return 0;
    }

#ifdef _WIN32
    // GUI mode
    qp::Logger::instance().info("Quant Platform starting in GUI mode...");
    return qp::MainWindow::run(hInstance, nCmdShow);
#endif
}
