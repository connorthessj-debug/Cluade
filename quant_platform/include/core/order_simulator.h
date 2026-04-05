#pragma once

#include "common/data_models.h"
#include <vector>

namespace qp {

class OrderSimulator {
public:
    void configure(const CostConfig& costs);
    Order submitOrder(Order order);
    std::vector<Trade> fillPendingOrders(const Bar& bar);
    void reset();

private:
    CostConfig m_costs;
    std::vector<Order> m_pendingOrders;
    int64_t m_nextOrderId = 1;
    int64_t m_nextTradeId = 1;

    double applySlippage(double price, OrderSide side) const;
    double applySpread(double price, OrderSide side) const;
    double calcCommission(double price, double qty) const;
};

} // namespace qp
