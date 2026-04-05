#include "core/order_simulator.h"
#include <algorithm>

namespace qp {

void OrderSimulator::configure(const CostConfig& costs) {
    m_costs = costs;
}

Order OrderSimulator::submitOrder(Order order) {
    order.id = m_nextOrderId++;
    order.status = OrderStatus::Pending;
    m_pendingOrders.push_back(order);
    return order;
}

std::vector<Trade> OrderSimulator::fillPendingOrders(const Bar& bar) {
    std::vector<Trade> trades;
    std::vector<Order> remaining;

    for (auto& order : m_pendingOrders) {
        bool fill = false;
        double fillPrice = 0.0;

        switch (order.type) {
            case OrderType::Market:
                fill = true;
                fillPrice = bar.open;
                break;

            case OrderType::Limit:
                if (order.side == OrderSide::Buy && bar.low <= order.price) {
                    fill = true;
                    fillPrice = std::min(bar.open, order.price);
                } else if (order.side == OrderSide::Sell && bar.high >= order.price) {
                    fill = true;
                    fillPrice = std::max(bar.open, order.price);
                }
                break;

            case OrderType::Stop:
                if (order.side == OrderSide::Buy && bar.high >= order.price) {
                    fill = true;
                    fillPrice = std::max(bar.open, order.price);
                } else if (order.side == OrderSide::Sell && bar.low <= order.price) {
                    fill = true;
                    fillPrice = std::min(bar.open, order.price);
                }
                break;
        }

        if (fill) {
            fillPrice = applySlippage(fillPrice, order.side);
            fillPrice = applySpread(fillPrice, order.side);
            double commission = calcCommission(fillPrice, order.quantity);

            order.fillPrice = fillPrice;
            order.commission = commission;
            order.slippage = std::abs(fillPrice - bar.open) * order.quantity;
            order.status = OrderStatus::Filled;
            order.timestamp = bar.date;

            Trade trade;
            trade.id = m_nextTradeId++;
            trade.symbol = order.symbol;
            trade.side = order.side;
            trade.quantity = order.quantity;
            trade.commission = commission;
            trade.slippage = order.slippage;

            if (order.side == OrderSide::Buy) {
                trade.entryPrice = fillPrice;
                trade.entryBarIndex = bar.index;
                trade.entryDate = bar.date;
            } else {
                trade.exitPrice = fillPrice;
                trade.exitBarIndex = bar.index;
                trade.exitDate = bar.date;
            }

            trades.push_back(trade);
        } else {
            remaining.push_back(order);
        }
    }

    m_pendingOrders = remaining;
    return trades;
}

void OrderSimulator::reset() {
    m_pendingOrders.clear();
    m_nextOrderId = 1;
    m_nextTradeId = 1;
}

double OrderSimulator::applySlippage(double price, OrderSide side) const {
    double slip = price * m_costs.slippageFactor;
    return (side == OrderSide::Buy) ? price + slip : price - slip;
}

double OrderSimulator::applySpread(double price, OrderSide side) const {
    double halfSpread = price * m_costs.spreadFactor * 0.5;
    return (side == OrderSide::Buy) ? price + halfSpread : price - halfSpread;
}

double OrderSimulator::calcCommission(double price, double qty) const {
    return price * qty * m_costs.commissionRate;
}

} // namespace qp
