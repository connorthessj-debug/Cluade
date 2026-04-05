#pragma once

#include "strategy/strategy_interface.h"
#include <vector>

namespace qp {

class MomentumStrategy : public IStrategy {
public:
    std::string name() const override;
    void init(const StrategyParams& params) override;
    std::vector<Order> onBar(const Bar& bar, const StrategyContext& ctx) override;
    void onOrderFilled(const Trade& trade) override;
    int requiredWarmupBars() const override;
    void reset() override;

private:
    int    m_lookbackPeriod = 10;
    double m_entryThreshold = 0.02;
    double m_exitThreshold  = -0.01;
    double m_positionSize   = 0.10;
    std::vector<double> m_closes;
};

} // namespace qp
