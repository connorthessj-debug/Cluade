#include "execution/paper_broker.h"
#include "common/logger.h"
#include <cmath>
#include <algorithm>

namespace qp {

PaperBroker::PaperBroker(double initialBalance, const CostConfig& costs)
    : m_balance(initialBalance), m_costs(costs)
{}

int64_t PaperBroker::submitOrder(const Order& order) {
    Order o = order;
    o.id = m_nextOrderId++;
    o.status = OrderStatus::Pending;
    m_pendingOrders.push_back(o);
    m_allOrders.push_back(o);
    Logger::instance().info("[Paper] Order submitted: id=" + std::to_string(o.id) +
                            " side=" + (o.side == OrderSide::Buy ? "BUY" : "SELL") +
                            " qty=" + std::to_string(o.quantity));
    return o.id;
}

bool PaperBroker::cancelOrder(int64_t orderId) {
    for (auto it = m_pendingOrders.begin(); it != m_pendingOrders.end(); ++it) {
        if (it->id == orderId) {
            it->status = OrderStatus::Cancelled;
            m_pendingOrders.erase(it);
            Logger::instance().info("[Paper] Order cancelled: id=" + std::to_string(orderId));
            return true;
        }
    }
    return false;
}

Position PaperBroker::getPosition() const { return m_position; }
double PaperBroker::getAccountBalance() const { return m_balance; }

void PaperBroker::onBarUpdate(const Bar& bar) {
    m_lastBar = bar;

    std::vector<Order> remaining;
    for (auto& order : m_pendingOrders) {
        tryFillOrder(order, bar);
        if (order.status == OrderStatus::Pending) {
            remaining.push_back(order);
        }
    }
    m_pendingOrders = remaining;

    // Mark to market
    if (m_position.side == PositionSide::Long && m_position.quantity > 0) {
        m_position.unrealizedPnl = (bar.close - m_position.avgEntryPrice) * m_position.quantity;
    }
}

void PaperBroker::tryFillOrder(Order& order, const Bar& bar) {
    double fillPrice = bar.open;

    // Apply costs
    double slip = fillPrice * m_costs.slippageFactor;
    double halfSpread = fillPrice * m_costs.spreadFactor * 0.5;
    if (order.side == OrderSide::Buy) {
        fillPrice += slip + halfSpread;
    } else {
        fillPrice -= slip + halfSpread;
    }

    double commission = fillPrice * order.quantity * m_costs.commissionRate;
    order.fillPrice = fillPrice;
    order.commission = commission;
    order.status = OrderStatus::Filled;
    order.timestamp = bar.date;

    if (order.side == OrderSide::Buy) {
        double cost = fillPrice * order.quantity + commission;
        if (cost > m_balance) {
            order.status = OrderStatus::Rejected;
            Logger::instance().warn("[Paper] Order rejected: insufficient balance");
            return;
        }
        m_balance -= cost;
        m_position.side = PositionSide::Long;
        m_position.quantity = order.quantity;
        m_position.avgEntryPrice = fillPrice;
        m_pendingEntryPrice = fillPrice;
        m_pendingEntryDate = bar.date;
        m_pendingEntryBar = bar.index;
    } else {
        double proceeds = fillPrice * order.quantity - commission;
        m_balance += proceeds;

        Trade trade;
        trade.id = m_nextTradeId++;
        trade.side = OrderSide::Sell;
        trade.entryPrice = m_pendingEntryPrice;
        trade.exitPrice = fillPrice;
        trade.quantity = order.quantity;
        trade.pnl = (fillPrice - m_pendingEntryPrice) * order.quantity - commission;
        trade.commission = commission;
        trade.entryDate = m_pendingEntryDate;
        trade.exitDate = bar.date;
        trade.entryBarIndex = m_pendingEntryBar;
        trade.exitBarIndex = bar.index;
        trade.holdingPeriod = static_cast<int>(bar.index - m_pendingEntryBar);
        m_filledTrades.push_back(trade);

        m_position.realizedPnl += trade.pnl;
        m_position.side = PositionSide::Flat;
        m_position.quantity = 0.0;
        m_position.avgEntryPrice = 0.0;
        m_position.unrealizedPnl = 0.0;
    }

    Logger::instance().info("[Paper] Order filled: id=" + std::to_string(order.id) +
                            " price=" + std::to_string(fillPrice));
}

} // namespace qp
