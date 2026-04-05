#pragma once

#include "strategy/strategy_interface.h"
#include <vector>

namespace qp {

// Example RSI strategy showing how to implement IStrategy.
// This can be registered in the strategy factory for use.
class RSIStrategy : public IStrategy {
public:
    std::string name() const override { return "rsi"; }
    void init(const StrategyParams& params) override;
    std::vector<Order> onBar(const Bar& bar, const StrategyContext& ctx) override;
    void onOrderFilled(const Trade& trade) override;
    int requiredWarmupBars() const override;
    void reset() override;

private:
    int    m_period       = 14;
    double m_oversold     = 30.0;
    double m_overbought   = 70.0;
    double m_positionSize = 0.10;
    std::vector<double> m_closes;

    double computeRSI() const;
};

} // namespace qp
