#include "execution/execution_engine.h"
#include "execution/paper_broker.h"
#include "common/logger.h"
#include "common/json.hpp"
#include <fstream>

namespace qp {

void ExecutionEngine::configure(const AppConfig& config, const std::string& executionConfigPath) {
    m_config = config;

    // Load execution config
    std::ifstream file(executionConfigPath);
    if (file.is_open()) {
        nlohmann::json j;
        try {
            file >> j;
            if (j.contains("maxPositionSize"))  m_riskLimits.maxPositionSize = j["maxPositionSize"].get<double>();
            if (j.contains("maxPositionPct"))    m_riskLimits.maxPositionPct  = j["maxPositionPct"].get<double>();
            if (j.contains("riskPerTrade"))      m_riskLimits.riskPerTrade    = j["riskPerTrade"].get<double>();
            if (j.contains("maxDailyLoss"))      m_riskLimits.maxDailyLoss    = j["maxDailyLoss"].get<double>();
            if (j.contains("maxDrawdownPct"))    m_riskLimits.maxDrawdownPct  = j["maxDrawdownPct"].get<double>();
        } catch (...) {
            Logger::instance().warn("Failed to parse execution config");
        }
    }

    m_broker = std::make_shared<PaperBroker>(config.initialCapital, config.costs);
}

void ExecutionEngine::runPaperTrading(const std::vector<Bar>& bars,
                                      IStrategy& strategy,
                                      const StrategyParams& params) {
    Logger& log = Logger::instance();
    log.info("[Execution] Starting paper trading: " + params.strategyName +
             " on " + std::to_string(bars.size()) + " bars");

    strategy.init(params);
    OrderManager orderMgr(m_broker);
    RiskManager riskMgr;
    riskMgr.configure(m_riskLimits);

    double peakEquity = m_config.initialCapital;

    for (const auto& bar : bars) {
        m_broker->onBarUpdate(bar);

        StrategyContext ctx;
        ctx.currentPosition = m_broker->getPosition();
        ctx.equity = m_broker->getAccountBalance();
        ctx.cash = ctx.equity;
        ctx.barIndex = bar.index;
        ctx.currentBar = &bar;
        ctx.bars = &bars;

        if (ctx.equity > peakEquity) peakEquity = ctx.equity;

        auto orders = strategy.onBar(bar, ctx);
        for (auto& order : orders) {
            bool allowed = riskMgr.checkOrder(order, ctx.currentPosition,
                                               ctx.equity, ctx.equity, peakEquity);
            if (allowed) {
                orderMgr.submit(order);
            }
        }
    }

    auto* paperBroker = dynamic_cast<PaperBroker*>(m_broker.get());
    if (paperBroker) {
        log.info("[Execution] Paper trading complete. Trades: " +
                 std::to_string(paperBroker->filledTrades().size()) +
                 ", Balance: $" + std::to_string(m_broker->getAccountBalance()));
    }
}

} // namespace qp
