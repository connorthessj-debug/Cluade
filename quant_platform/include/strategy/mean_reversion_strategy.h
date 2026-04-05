#pragma once

#include "strategy/strategy_interface.h"
#include <vector>

namespace qp {

class MeanReversionStrategy : public IStrategy {
public:
    std::string name() const override;
    void init(const StrategyParams& params) override;
    std::vector<Order> onBar(const Bar& bar, const StrategyContext& ctx) override;
    void onOrderFilled(const Trade& trade) override;
    int requiredWarmupBars() const override;
    void reset() override;

private:
    int    m_period          = 20;
    double m_stdDevMultiplier = 2.0;
    double m_positionSize    = 0.10;
    std::vector<double> m_closes;

    double calcSMA() const;
    double calcStdDev(double mean) const;
};

} // namespace qp
