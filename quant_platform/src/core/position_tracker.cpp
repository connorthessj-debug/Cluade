#include "core/position_tracker.h"
#include <cmath>

namespace qp {

void PositionTracker::reset(double initialCapital) {
    m_position = Position();
    m_cash = initialCapital;
    m_equity = initialCapital;
    m_equityCurve.clear();
    m_completedTrades.clear();
    m_pendingEntryPrice = 0.0;
    m_pendingEntryBar = 0;
    m_pendingEntryDate.clear();
}

void PositionTracker::processFill(const Trade& fill) {
    if (fill.side == OrderSide::Buy) {
        // Opening a long position
        double cost = fill.entryPrice * fill.quantity + fill.commission;
        m_cash -= cost;
        m_position.side = PositionSide::Long;
        m_position.quantity = fill.quantity;
        m_position.avgEntryPrice = fill.entryPrice;
        m_pendingEntryPrice = fill.entryPrice;
        m_pendingEntryBar = fill.entryBarIndex;
        m_pendingEntryDate = fill.entryDate;
    } else {
        // Closing a long position
        double proceeds = fill.exitPrice * fill.quantity - fill.commission;
        m_cash += proceeds;

        Trade completed = fill;
        completed.entryPrice = m_pendingEntryPrice;
        completed.entryBarIndex = m_pendingEntryBar;
        completed.entryDate = m_pendingEntryDate;
        completed.pnl = (fill.exitPrice - m_pendingEntryPrice) * fill.quantity
                        - fill.commission;
        completed.holdingPeriod = static_cast<int>(fill.exitBarIndex - m_pendingEntryBar);
        m_completedTrades.push_back(completed);

        m_position.realizedPnl += completed.pnl;
        m_position.side = PositionSide::Flat;
        m_position.quantity = 0.0;
        m_position.avgEntryPrice = 0.0;
        m_position.unrealizedPnl = 0.0;
    }
}

void PositionTracker::markToMarket(double currentPrice) {
    if (m_position.side == PositionSide::Long && m_position.quantity > 0) {
        m_position.unrealizedPnl =
            (currentPrice - m_position.avgEntryPrice) * m_position.quantity;
        m_equity = m_cash + currentPrice * m_position.quantity;
    } else {
        m_position.unrealizedPnl = 0.0;
        m_equity = m_cash;
    }
    m_equityCurve.push_back(m_equity);
}

Position PositionTracker::currentPosition() const { return m_position; }
double PositionTracker::equity() const { return m_equity; }
double PositionTracker::cash() const { return m_cash; }
const std::vector<double>& PositionTracker::equityCurve() const { return m_equityCurve; }
const std::vector<Trade>& PositionTracker::completedTrades() const { return m_completedTrades; }

} // namespace qp
