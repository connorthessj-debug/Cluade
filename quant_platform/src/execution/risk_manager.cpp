#include "execution/risk_manager.h"
#include "common/logger.h"

namespace qp {

void RiskManager::configure(const RiskLimits& limits) {
    m_limits = limits;
}

bool RiskManager::checkOrder(const Order& order, const Position& position,
                             double accountBalance, double currentEquity,
                             double peakEquity) const
{
    Logger& log = Logger::instance();

    // Check max position size
    double orderValue = order.quantity * order.price;
    if (order.type == OrderType::Market) {
        orderValue = order.quantity; // price unknown, check quantity
    }

    if (order.side == OrderSide::Buy) {
        double newPositionQty = position.quantity + order.quantity;
        if (newPositionQty > m_limits.maxPositionSize) {
            log.warn("[Risk] Order rejected: exceeds max position size " +
                     std::to_string(m_limits.maxPositionSize));
            return false;
        }

        // Check position as % of equity
        double pctOfEquity = (order.quantity * order.price) / currentEquity;
        if (pctOfEquity > m_limits.maxPositionPct && order.price > 0) {
            log.warn("[Risk] Order rejected: position " + std::to_string(pctOfEquity * 100.0) +
                     "% exceeds max " + std::to_string(m_limits.maxPositionPct * 100.0) + "%");
            return false;
        }
    }

    // Check drawdown limit
    if (peakEquity > 0.0) {
        double dd = (peakEquity - currentEquity) / peakEquity;
        if (dd > m_limits.maxDrawdownPct) {
            log.warn("[Risk] Order rejected: drawdown " + std::to_string(dd * 100.0) +
                     "% exceeds max " + std::to_string(m_limits.maxDrawdownPct * 100.0) + "%");
            return false;
        }
    }

    return true;
}

} // namespace qp
