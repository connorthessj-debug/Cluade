#include "strategy/momentum_strategy.h"
#include <cmath>

namespace qp {

std::string MomentumStrategy::name() const { return "momentum"; }

void MomentumStrategy::init(const StrategyParams& params) {
    m_lookbackPeriod = static_cast<int>(params.get("lookbackPeriod", 10));
    m_entryThreshold = params.get("entryThreshold", 0.02);
    m_exitThreshold  = params.get("exitThreshold", -0.01);
    m_positionSize   = params.get("positionSize", 0.10);
    m_closes.clear();
}

std::vector<Order> MomentumStrategy::onBar(const Bar& bar, const StrategyContext& ctx) {
    std::vector<Order> orders;
    m_closes.push_back(bar.close);

    if (static_cast<int>(m_closes.size()) <= m_lookbackPeriod) {
        return orders;
    }

    // Rate of change
    double pastClose = m_closes[m_closes.size() - 1 - static_cast<size_t>(m_lookbackPeriod)];
    if (pastClose <= 0.0) return orders;
    double roc = (bar.close - pastClose) / pastClose;

    bool isFlat = (ctx.currentPosition.side == PositionSide::Flat);
    bool isLong = (ctx.currentPosition.side == PositionSide::Long);

    if (isFlat && roc > m_entryThreshold) {
        // Buy signal
        double capitalToUse = ctx.equity * m_positionSize;
        double qty = std::floor(capitalToUse / bar.close);
        if (qty > 0) {
            Order ord;
            ord.side = OrderSide::Buy;
            ord.type = OrderType::Market;
            ord.quantity = qty;
            ord.barIndex = bar.index;
            orders.push_back(ord);
        }
    } else if (isLong && roc < m_exitThreshold) {
        // Sell signal — close position
        Order ord;
        ord.side = OrderSide::Sell;
        ord.type = OrderType::Market;
        ord.quantity = ctx.currentPosition.quantity;
        ord.barIndex = bar.index;
        orders.push_back(ord);
    }

    return orders;
}

void MomentumStrategy::onOrderFilled(const Trade& /*trade*/) {
    // No additional state tracking needed
}

int MomentumStrategy::requiredWarmupBars() const {
    return m_lookbackPeriod;
}

void MomentumStrategy::reset() {
    m_closes.clear();
}

} // namespace qp
