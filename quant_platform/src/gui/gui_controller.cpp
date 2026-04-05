#ifdef _WIN32

#include "gui/gui_controller.h"
#include "gui/gui_utils.h"
#include "common/config_loader.h"
#include "io/csv_reader.h"
#include "core/backtest_engine.h"
#include "strategy/strategy_interface.h"
#include "metrics/metrics_engine.h"
#include "montecarlo/monte_carlo_engine.h"
#include "optimization/grid_optimizer.h"
#include "truth/truth_engine.h"
#include "execution/execution_engine.h"
#include <sstream>
#include <iomanip>
#include <memory>

namespace qp {

void GuiController::init(GuiPanels* panels) {
    m_panels = panels;
    m_config = loadAppConfig("config/app_config.json");
}

void GuiController::setStatus(const std::string& text) {
    if (m_panels && m_panels->hStatusLabel) {
        setControlText(m_panels->hStatusLabel, text);
    }
}

void GuiController::report(const std::string& text) {
    if (m_panels && m_panels->hReportEdit) {
        appendToReport(m_panels->hReportEdit, text);
    }
}

std::string GuiController::getSelectedStrategy() const {
    if (!m_panels || !m_panels->hStrategyCombo) return "momentum";
    int idx = static_cast<int>(SendMessageA(m_panels->hStrategyCombo, CB_GETCURSEL, 0, 0));
    char buf[256] = {};
    SendMessageA(m_panels->hStrategyCombo, CB_GETLBTEXT, static_cast<WPARAM>(idx), reinterpret_cast<LPARAM>(buf));
    return std::string(buf);
}

StrategyParams GuiController::getParamsFromUI() const {
    StrategyParams p;
    p.strategyName = getSelectedStrategy();

    if (p.strategyName == "momentum") {
        p.params["lookbackPeriod"] = std::stod(getControlText(m_panels->hParam1Edit));
        p.params["entryThreshold"] = std::stod(getControlText(m_panels->hParam2Edit));
        p.params["exitThreshold"]  = std::stod(getControlText(m_panels->hParam3Edit));
        p.params["positionSize"]   = std::stod(getControlText(m_panels->hParam4Edit));
    } else {
        p.params["period"]           = std::stod(getControlText(m_panels->hParam1Edit));
        p.params["stdDevMultiplier"] = std::stod(getControlText(m_panels->hParam2Edit));
        p.params["positionSize"]     = std::stod(getControlText(m_panels->hParam4Edit));
    }
    return p;
}

void GuiController::onLoadData(HWND parent) {
    OPENFILENAMEA ofn = {};
    char fileName[MAX_PATH] = {};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = parent;
    ofn.lpstrFilter = "CSV Files\0*.csv\0All Files\0*.*\0";
    ofn.lpstrFile = fileName;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;

    if (GetOpenFileNameA(&ofn)) {
        try {
            m_bars = loadBarsFromCSV(fileName);
            m_dataLoaded = true;
            std::string info = std::string(fileName) + " (" + std::to_string(m_bars.size()) + " bars)";
            setControlText(m_panels->hDataLabel, info);
            setStatus("Data loaded: " + std::to_string(m_bars.size()) + " bars");
            report("Loaded " + std::to_string(m_bars.size()) + " bars from " + fileName);
        } catch (const std::exception& e) {
            showError(parent, std::string("Failed to load data: ") + e.what());
        }
    }
}

void GuiController::onRunBacktest() {
    if (!m_dataLoaded || m_bars.empty()) {
        report("Error: No data loaded. Please load data first.");
        return;
    }

    setStatus("Running backtest...");
    try {
        auto strategy = createStrategy(getSelectedStrategy());
        if (!strategy) {
            report("Error: Unknown strategy: " + getSelectedStrategy());
            return;
        }

        StrategyParams params = getParamsFromUI();
        BacktestEngine engine;
        engine.configure(m_config);
        m_lastSnapshot = engine.run(m_bars, *strategy, params);

        MetricsEngine metricsEngine(m_config);
        m_lastMetrics = metricsEngine.compute(m_lastSnapshot);

        std::ostringstream oss;
        oss << std::fixed << std::setprecision(2);
        oss << "===== Backtest Results =====\r\n";
        oss << "Strategy:      " << params.strategyName << "\r\n";
        oss << "Trades:        " << m_lastMetrics.totalTrades << "\r\n";
        oss << "Final Equity:  $" << m_lastSnapshot.finalEquity << "\r\n";
        oss << "Total Return:  " << (m_lastMetrics.totalReturn * 100.0) << "%\r\n";
        oss << "CAGR:          " << (m_lastMetrics.cagr * 100.0) << "%\r\n";
        oss << "Sharpe:        " << m_lastMetrics.sharpeRatio << "\r\n";
        oss << "Sortino:       " << m_lastMetrics.sortinoRatio << "\r\n";
        oss << "Max Drawdown:  " << (m_lastMetrics.maxDrawdown * 100.0) << "%\r\n";
        oss << "Win Rate:      " << (m_lastMetrics.winRate * 100.0) << "%\r\n";
        oss << "Profit Factor: " << m_lastMetrics.profitFactor << "\r\n";
        oss << "Expectancy:    " << m_lastMetrics.expectancy << "\r\n";
        oss << "Avg Trade:     $" << m_lastMetrics.avgTrade << "\r\n";
        oss << "============================\r\n";
        report(oss.str());

        setStatus("Backtest complete: " + std::to_string(m_lastMetrics.totalTrades) + " trades");
    } catch (const std::exception& e) {
        report(std::string("Backtest error: ") + e.what());
        setStatus("Backtest failed");
    }
}

void GuiController::onRunOptimizer() {
    if (!m_dataLoaded || m_bars.empty()) {
        report("Error: No data loaded.");
        return;
    }

    setStatus("Running optimizer...");
    try {
        auto strategy = createStrategy(getSelectedStrategy());
        if (!strategy) return;

        std::vector<ParamRange> ranges;
        if (getSelectedStrategy() == "momentum") {
            ranges.push_back({"lookbackPeriod", 5, 30, 5});
            ranges.push_back({"entryThreshold", 0.01, 0.05, 0.01});
            ranges.push_back({"exitThreshold", -0.03, 0.0, 0.01});
            ranges.push_back({"positionSize", 0.05, 0.20, 0.05});
        } else {
            ranges.push_back({"period", 10, 30, 5});
            ranges.push_back({"stdDevMultiplier", 1.5, 3.0, 0.5});
            ranges.push_back({"positionSize", 0.05, 0.20, 0.05});
        }

        GridOptimizer optimizer;
        auto result = optimizer.optimize(m_bars, *strategy, ranges,
                                          ObjectiveFunction::Sharpe, m_config);

        std::ostringstream oss;
        oss << std::fixed << std::setprecision(4);
        oss << "===== Optimization Results =====\r\n";
        oss << "Evaluated: " << result.evaluatedCount << " / " << result.totalCombinations << "\r\n";
        oss << "Best Score: " << result.bestScore << "\r\n";
        oss << "Best Params:\r\n";
        for (auto& [k, v] : result.bestParams.params) {
            oss << "  " << k << " = " << v << "\r\n";
        }
        oss << "Best Sharpe: " << result.bestMetrics.sharpeRatio << "\r\n";
        oss << "================================\r\n";
        report(oss.str());

        setStatus("Optimization complete");
    } catch (const std::exception& e) {
        report(std::string("Optimizer error: ") + e.what());
        setStatus("Optimization failed");
    }
}

void GuiController::onRunTruthEngine() {
    if (m_lastSnapshot.trades.empty()) {
        report("Error: Run a backtest first.");
        return;
    }

    setStatus("Running Truth Engine...");
    try {
        auto strategy = createStrategy(getSelectedStrategy());
        if (!strategy) return;

        StrategyParams params = getParamsFromUI();
        TruthEngine truthEngine;
        truthEngine.loadConfig("config/truth_engine_config.json");
        TruthReport tr = truthEngine.evaluate(m_lastSnapshot, m_lastMetrics,
                                               m_bars, *strategy, params, m_config);

        std::ostringstream oss;
        oss << std::fixed << std::setprecision(3);
        oss << "===== Truth Report =====\r\n";
        oss << "Overall Score:     " << tr.overallScore << "\r\n";
        oss << "Robustness:        " << tr.robustnessScore << "\r\n";
        oss << "Overfit Risk:      " << tr.overfitRisk << "\r\n";
        oss << "Exec Fragility:    " << tr.executionFragility << "\r\n";
        oss << "Cost Sensitivity:  " << tr.costSensitivity << "\r\n";
        oss << "Regime Dependence: " << tr.regimeDependence << "\r\n";
        oss << "Paper Trading:     " << (tr.passForPaperTrading ? "PASS" : "FAIL") << "\r\n";
        oss << "Live Capital:      " << (tr.passForLiveCapital ? "PASS" : "FAIL") << "\r\n";

        if (!tr.criticalFailures.empty()) {
            oss << "Critical Failures:\r\n";
            for (auto& f : tr.criticalFailures) oss << "  - " << f << "\r\n";
        }
        for (auto& c : tr.checks) {
            oss << "  [" << (c.passed ? "PASS" : "FAIL") << "] " << c.checkName
                << " (score=" << c.score << ")\r\n";
        }
        oss << "========================\r\n";
        report(oss.str());

        setStatus("Truth Engine complete");
    } catch (const std::exception& e) {
        report(std::string("Truth Engine error: ") + e.what());
        setStatus("Truth Engine failed");
    }
}

void GuiController::onRunPaperTrading() {
    if (!m_dataLoaded || m_bars.empty()) {
        report("Error: No data loaded.");
        return;
    }

    setStatus("Running paper trading...");
    try {
        auto strategy = createStrategy(getSelectedStrategy());
        if (!strategy) return;

        StrategyParams params = getParamsFromUI();
        ExecutionEngine execEngine;
        execEngine.configure(m_config, "config/execution_config.json");
        execEngine.runPaperTrading(m_bars, *strategy, params);

        report("Paper trading complete. See log for details.");
        setStatus("Paper trading complete");
    } catch (const std::exception& e) {
        report(std::string("Paper trading error: ") + e.what());
        setStatus("Paper trading failed");
    }
}

} // namespace qp

#endif // _WIN32
