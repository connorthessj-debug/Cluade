#pragma once

#include "common/data_models.h"
#include <vector>

namespace qp {

class MonteCarloEngine {
public:
    MonteCarloSummary run(const std::vector<Trade>& trades,
                          double initialCapital,
                          int numSimulations,
                          unsigned int seed = 0);

    MonteCarloSummary runSlippagePerturbation(
        const std::vector<Trade>& trades,
        double initialCapital,
        int numSimulations,
        double slippageNoiseStdDev = 0.001,
        unsigned int seed = 0);

    MonteCarloSummary runMissedTrades(
        const std::vector<Trade>& trades,
        double initialCapital,
        int numSimulations,
        double missedRate = 0.15,
        unsigned int seed = 0);

private:
    struct MCDrawdownInfo {
        double maxDD = 0.0;
    };

    double computePercentile(std::vector<double>& sorted, double pct) const;
    MCDrawdownInfo computeMaxDD(const std::vector<double>& equityCurve) const;
};

} // namespace qp
