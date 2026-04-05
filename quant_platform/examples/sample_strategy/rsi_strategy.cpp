#include "rsi_strategy.h"
#include <cmath>

namespace qp {

void RSIStrategy::init(const StrategyParams& params) {
    m_period       = static_cast<int>(params.get("rsiPeriod", 14));
    m_oversold     = params.get("oversold", 30.0);
    m_overbought   = params.get("overbought", 70.0);
    m_positionSize = params.get("positionSize", 0.10);
    m_closes.clear();
}

std::vector<Order> RSIStrategy::onBar(const Bar& bar, const StrategyContext& ctx) {
    std::vector<Order> orders;
    m_closes.push_back(bar.close);

    if (static_cast<int>(m_closes.size()) <= m_period) {
        return orders;
    }

    double rsi = computeRSI();
    bool isFlat = (ctx.currentPosition.side == PositionSide::Flat);
    bool isLong = (ctx.currentPosition.side == PositionSide::Long);

    if (isFlat && rsi < m_oversold) {
        double qty = std::floor((ctx.equity * m_positionSize) / bar.close);
        if (qty > 0) {
            Order ord;
            ord.side = OrderSide::Buy;
            ord.type = OrderType::Market;
            ord.quantity = qty;
            ord.barIndex = bar.index;
            orders.push_back(ord);
        }
    } else if (isLong && rsi > m_overbought) {
        Order ord;
        ord.side = OrderSide::Sell;
        ord.type = OrderType::Market;
        ord.quantity = ctx.currentPosition.quantity;
        ord.barIndex = bar.index;
        orders.push_back(ord);
    }

    return orders;
}

void RSIStrategy::onOrderFilled(const Trade& /*trade*/) {}

int RSIStrategy::requiredWarmupBars() const {
    return m_period + 1;
}

void RSIStrategy::reset() {
    m_closes.clear();
}

double RSIStrategy::computeRSI() const {
    if (static_cast<int>(m_closes.size()) < m_period + 1) return 50.0;

    double gainSum = 0.0;
    double lossSum = 0.0;
    size_t start = m_closes.size() - static_cast<size_t>(m_period) - 1;
    for (size_t i = start + 1; i < m_closes.size(); i++) {
        double change = m_closes[i] - m_closes[i - 1];
        if (change > 0.0) gainSum += change;
        else lossSum += std::abs(change);
    }

    double avgGain = gainSum / static_cast<double>(m_period);
    double avgLoss = lossSum / static_cast<double>(m_period);

    if (avgLoss < 1e-10) return 100.0;
    double rs = avgGain / avgLoss;
    return 100.0 - (100.0 / (1.0 + rs));
}

} // namespace qp
