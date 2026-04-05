#pragma once

#include "common/data_models.h"

namespace qp {

struct RiskLimits {
    double maxPositionSize  = 1000.0;
    double maxPositionPct   = 0.25;
    double riskPerTrade     = 0.02;
    double maxDailyLoss     = 5000.0;
    double maxDrawdownPct   = 0.15;
};

class RiskManager {
public:
    void configure(const RiskLimits& limits);
    bool checkOrder(const Order& order, const Position& position,
                    double accountBalance, double currentEquity, double peakEquity) const;

private:
    RiskLimits m_limits;
};

} // namespace qp
