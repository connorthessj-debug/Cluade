#pragma once

#include "common/data_models.h"
#include "strategy/strategy_interface.h"
#include <string>
#include <vector>

namespace qp {

class TruthEngine {
public:
    void loadConfig(const std::string& configPath);

    TruthReport evaluate(
        const BacktestSnapshot& snapshot,
        const MetricsSummary& metrics,
        const std::vector<Bar>& bars,
        IStrategy& strategy,
        const StrategyParams& params,
        const AppConfig& appConfig);

private:
    void applyHardFailRules(TruthReport& report, const MetricsSummary& metrics);

    std::vector<double> m_slippageMultipliers = {2.0, 5.0};
    double m_spreadShockMultiplier  = 3.0;
    double m_paramPerturbPct        = 0.10;
    double m_missedTradeRate        = 0.15;
    double m_hardFailMaxDrawdown    = 0.40;
    double m_hardFailMCFailureRate  = 0.30;
    double m_hardFailDegradationRatio = 0.30;
    double m_minSharpeForLive       = 0.5;
    double m_minWinRateForLive      = 0.35;
    double m_regimeSplitRatio       = 0.5;
};

} // namespace qp
