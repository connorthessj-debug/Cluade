#pragma once

#include "common/data_models.h"
#include "execution/broker_adapter.h"
#include "execution/order_manager.h"
#include "execution/risk_manager.h"
#include "strategy/strategy_interface.h"
#include <vector>
#include <memory>

namespace qp {

class ExecutionEngine {
public:
    void configure(const AppConfig& config, const std::string& executionConfigPath);

    void runPaperTrading(const std::vector<Bar>& bars,
                         IStrategy& strategy,
                         const StrategyParams& params);

private:
    AppConfig m_config;
    RiskLimits m_riskLimits;
    std::shared_ptr<IBrokerAdapter> m_broker;
};

} // namespace qp
