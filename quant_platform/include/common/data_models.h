#pragma once

#include <string>
#include <vector>
#include <cstdint>
#include <limits>
#include <map>

namespace qp {

// ============================================================
// Enums
// ============================================================

enum class OrderSide { Buy, Sell };
enum class OrderType { Market, Limit, Stop };
enum class OrderStatus { Pending, Filled, Cancelled, Rejected };
enum class PositionSide { Flat, Long, Short };

// ============================================================
// Bar / Candle
// ============================================================

struct Bar {
    std::string date;
    double open   = 0.0;
    double high   = 0.0;
    double low    = 0.0;
    double close  = 0.0;
    double volume = 0.0;
    int64_t index = 0;
};

// ============================================================
// Order
// ============================================================

struct Order {
    int64_t     id        = 0;
    std::string symbol;
    OrderSide   side      = OrderSide::Buy;
    OrderType   type      = OrderType::Market;
    OrderStatus status    = OrderStatus::Pending;
    double      quantity  = 0.0;
    double      price     = 0.0;   // limit/stop price
    double      fillPrice = 0.0;
    double      commission = 0.0;
    double      slippage  = 0.0;
    int64_t     barIndex  = 0;
    std::string timestamp;
};

// ============================================================
// Trade
// ============================================================

struct Trade {
    int64_t     id            = 0;
    std::string symbol;
    OrderSide   side          = OrderSide::Buy;
    double      entryPrice    = 0.0;
    double      exitPrice     = 0.0;
    double      quantity      = 0.0;
    double      pnl           = 0.0;
    double      commission    = 0.0;
    double      slippage      = 0.0;
    int64_t     entryBarIndex = 0;
    int64_t     exitBarIndex  = 0;
    std::string entryDate;
    std::string exitDate;
    int         holdingPeriod = 0;
};

// ============================================================
// Position
// ============================================================

struct Position {
    std::string  symbol;
    PositionSide side          = PositionSide::Flat;
    double       quantity      = 0.0;
    double       avgEntryPrice = 0.0;
    double       unrealizedPnl = 0.0;
    double       realizedPnl   = 0.0;
};

// ============================================================
// StrategyParams
// ============================================================

struct StrategyParams {
    std::string strategyName;
    std::map<std::string, double> params;

    double get(const std::string& key, double defaultVal = 0.0) const {
        auto it = params.find(key);
        return (it != params.end()) ? it->second : defaultVal;
    }
};

// ============================================================
// BacktestSnapshot
// ============================================================

struct BacktestSnapshot {
    std::string           strategyName;
    StrategyParams        params;
    double                initialCapital  = 100000.0;
    double                finalEquity     = 0.0;
    std::vector<double>   equityCurve;
    std::vector<Trade>    trades;
    std::vector<Order>    orders;
    std::vector<Bar>      bars;
    double                totalCommission = 0.0;
    double                totalSlippage   = 0.0;
};

// ============================================================
// MetricsSummary
// ============================================================

struct MetricsSummary {
    double totalReturn       = 0.0;
    double cagr              = 0.0;
    double sharpeRatio       = 0.0;
    double sortinoRatio      = 0.0;
    double maxDrawdown       = 0.0;
    int    maxDrawdownDuration = 0;  // in bars
    double expectancy        = 0.0;
    double profitFactor      = 0.0;
    double winRate           = 0.0;
    double avgTrade          = 0.0;
    int    totalTrades       = 0;
    int    winningTrades     = 0;
    int    losingTrades      = 0;
    double grossProfit       = 0.0;
    double grossLoss         = 0.0;
};

// ============================================================
// MonteCarloSummary
// ============================================================

struct MonteCarloSummary {
    int    numSimulations     = 0;
    double medianFinalEquity  = 0.0;
    double p5FinalEquity      = 0.0;
    double p25FinalEquity     = 0.0;
    double p75FinalEquity     = 0.0;
    double p95FinalEquity     = 0.0;
    double failureRate        = 0.0;  // fraction below initial capital
    double worstDrawdown      = 0.0;
    double medianDrawdown     = 0.0;
    std::string mode;  // "reshuffle", "slippage", "missed"
};

// ============================================================
// Walk-Forward Models
// ============================================================

struct WalkForwardWindowResult {
    int             windowIndex     = 0;
    int             isStartBar      = 0;
    int             isEndBar        = 0;
    int             oosStartBar     = 0;
    int             oosEndBar       = 0;
    StrategyParams  bestParams;
    MetricsSummary  inSampleMetrics;
    MetricsSummary  outOfSampleMetrics;
    double          degradationRatio = 0.0; // OOS Sharpe / IS Sharpe
};

struct WalkForwardReport {
    std::string windowType; // "rolling" or "anchored"
    int         numWindows  = 0;
    double      inSampleRatio = 0.7;
    std::vector<WalkForwardWindowResult> windows;
    double      avgDegradation  = 0.0;
    double      consistencyScore = 0.0;
    bool        passed           = false;
};

// ============================================================
// OptimizationResult
// ============================================================

struct OptimizationResult {
    StrategyParams  bestParams;
    double          bestScore       = -std::numeric_limits<double>::infinity();
    std::string     objectiveName;
    int             totalCombinations = 0;
    int             evaluatedCount    = 0;
    MetricsSummary  bestMetrics;
};

// ============================================================
// TruthReport
// ============================================================

struct TruthCheckResult {
    std::string checkName;
    double      score       = 0.0;   // 0.0 to 1.0
    bool        passed      = false;
    std::string detail;
};

struct TruthReport {
    double overallScore       = 0.0;
    double robustnessScore    = 0.0;
    double overfitRisk        = 0.0;
    double executionFragility = 0.0;
    double costSensitivity    = 0.0;
    double regimeDependence   = 0.0;
    bool   passForPaperTrading = false;
    bool   passForLiveCapital  = false;
    std::vector<TruthCheckResult> checks;
    std::vector<std::string>      criticalFailures;
    std::vector<std::string>      recommendedActions;
};

// ============================================================
// AppConfig
// ============================================================

struct CostConfig {
    double commissionRate = 0.001;
    double slippageFactor = 0.0005;
    double spreadFactor   = 0.0001;
};

struct AppConfig {
    std::string dataPath         = "data/sample/sample_data.csv";
    std::string defaultStrategy  = "momentum";
    double      initialCapital   = 100000.0;
    CostConfig  costs;
    std::string logLevel         = "info";
    std::string configDir        = "config";
    std::string outputDir        = "output";
    int         monteCarloSims   = 1000;
    double      riskFreeRate     = 0.02;
    int         tradingDaysPerYear = 252;
};

} // namespace qp
