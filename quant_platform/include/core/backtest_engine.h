#pragma once

#include "common/data_models.h"
#include "core/order_simulator.h"
#include "core/position_tracker.h"
#include "strategy/strategy_interface.h"
#include <vector>

namespace qp {

class BacktestEngine {
public:
    void configure(const AppConfig& config);
    BacktestSnapshot run(const std::vector<Bar>& bars,
                         IStrategy& strategy,
                         const StrategyParams& params);

private:
    AppConfig m_config;
    OrderSimulator m_orderSim;
    PositionTracker m_posTracker;
};

} // namespace qp
