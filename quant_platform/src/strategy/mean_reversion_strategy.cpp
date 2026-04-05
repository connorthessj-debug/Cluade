#include "strategy/mean_reversion_strategy.h"
#include <cmath>
#include <numeric>

namespace qp {

std::string MeanReversionStrategy::name() const { return "mean_reversion"; }

void MeanReversionStrategy::init(const StrategyParams& params) {
    m_period           = static_cast<int>(params.get("period", 20));
    m_stdDevMultiplier = params.get("stdDevMultiplier", 2.0);
    m_positionSize     = params.get("positionSize", 0.10);
    m_closes.clear();
}

std::vector<Order> MeanReversionStrategy::onBar(const Bar& bar, const StrategyContext& ctx) {
    std::vector<Order> orders;
    m_closes.push_back(bar.close);

    if (static_cast<int>(m_closes.size()) < m_period) {
        return orders;
    }

    double sma = calcSMA();
    double stddev = calcStdDev(sma);
    if (stddev <= 0.0) return orders;

    double upperBand = sma + m_stdDevMultiplier * stddev;
    double lowerBand = sma - m_stdDevMultiplier * stddev;

    bool isFlat  = (ctx.currentPosition.side == PositionSide::Flat);
    bool isLong  = (ctx.currentPosition.side == PositionSide::Long);

    if (isFlat && bar.close < lowerBand) {
        // Price below lower band — buy (mean reversion expects bounce)
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
    } else if (isLong && bar.close > upperBand) {
        // Price above upper band — sell (mean reversion expects pullback)
        Order ord;
        ord.side = OrderSide::Sell;
        ord.type = OrderType::Market;
        ord.quantity = ctx.currentPosition.quantity;
        ord.barIndex = bar.index;
        orders.push_back(ord);
    }

    return orders;
}

void MeanReversionStrategy::onOrderFilled(const Trade& /*trade*/) {}

int MeanReversionStrategy::requiredWarmupBars() const {
    return m_period;
}

void MeanReversionStrategy::reset() {
    m_closes.clear();
}

double MeanReversionStrategy::calcSMA() const {
    int n = m_period;
    double sum = 0.0;
    for (int i = static_cast<int>(m_closes.size()) - n; i < static_cast<int>(m_closes.size()); i++) {
        sum += m_closes[static_cast<size_t>(i)];
    }
    return sum / n;
}

double MeanReversionStrategy::calcStdDev(double mean) const {
    int n = m_period;
    double sumSq = 0.0;
    for (int i = static_cast<int>(m_closes.size()) - n; i < static_cast<int>(m_closes.size()); i++) {
        double diff = m_closes[static_cast<size_t>(i)] - mean;
        sumSq += diff * diff;
    }
    return std::sqrt(sumSq / n);
}

} // namespace qp
