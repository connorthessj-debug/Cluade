#pragma once

#include "common/data_models.h"

namespace qp {

class MetricsEngine {
public:
    explicit MetricsEngine(const AppConfig& config);
    MetricsSummary compute(const BacktestSnapshot& snapshot) const;

private:
    double m_riskFreeRate     = 0.02;
    int    m_tradingDaysPerYear = 252;
};

} // namespace qp
