#include "core/backtest_engine.h"
#include "common/logger.h"

namespace qp {

void BacktestEngine::configure(const AppConfig& config) {
    m_config = config;
}

BacktestSnapshot BacktestEngine::run(const std::vector<Bar>& bars,
                                     IStrategy& strategy,
                                     const StrategyParams& params) {
    Logger& log = Logger::instance();
    log.info("Starting backtest: " + params.strategyName +
             " on " + std::to_string(bars.size()) + " bars");

    m_orderSim.configure(m_config.costs);
    m_orderSim.reset();
    m_posTracker.reset(m_config.initialCapital);
    strategy.init(params);

    BacktestSnapshot snapshot;
    snapshot.strategyName = params.strategyName;
    snapshot.params = params;
    snapshot.initialCapital = m_config.initialCapital;
    snapshot.bars = bars;

    for (size_t i = 0; i < bars.size(); i++) {
        const Bar& bar = bars[i];

        // Fill pending orders from previous bar's signals
        auto fills = m_orderSim.fillPendingOrders(bar);
        for (auto& fill : fills) {
            m_posTracker.processFill(fill);
            strategy.onOrderFilled(fill);
            snapshot.orders.push_back(Order()); // record order
            snapshot.totalCommission += fill.commission;
            snapshot.totalSlippage += fill.slippage;
        }

        // Build strategy context
        StrategyContext ctx;
        ctx.currentPosition = m_posTracker.currentPosition();
        ctx.equity = m_posTracker.equity();
        ctx.cash = m_posTracker.cash();
        ctx.barIndex = bar.index;
        ctx.currentBar = &bar;
        ctx.bars = &bars;

        // Get strategy signals
        auto orders = strategy.onBar(bar, ctx);
        for (auto& ord : orders) {
            auto submitted = m_orderSim.submitOrder(ord);
            snapshot.orders.push_back(submitted);
        }

        // Mark to market
        m_posTracker.markToMarket(bar.close);
    }

    snapshot.equityCurve = m_posTracker.equityCurve();
    snapshot.trades = m_posTracker.completedTrades();
    snapshot.finalEquity = m_posTracker.equity();

    log.info("Backtest complete: " + std::to_string(snapshot.trades.size()) +
             " trades, final equity: $" + std::to_string(snapshot.finalEquity));

    return snapshot;
}

} // namespace qp
