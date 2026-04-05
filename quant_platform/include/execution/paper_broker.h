#pragma once

#include "execution/broker_adapter.h"
#include "common/data_models.h"
#include <vector>
#include <map>

namespace qp {

class PaperBroker : public IBrokerAdapter {
public:
    PaperBroker(double initialBalance, const CostConfig& costs);

    int64_t submitOrder(const Order& order) override;
    bool cancelOrder(int64_t orderId) override;
    Position getPosition() const override;
    double getAccountBalance() const override;
    void onBarUpdate(const Bar& bar) override;
    std::string name() const override { return "paper"; }

    const std::vector<Trade>& filledTrades() const { return m_filledTrades; }
    const std::vector<Order>& allOrders() const { return m_allOrders; }

private:
    void tryFillOrder(Order& order, const Bar& bar);

    double    m_balance;
    CostConfig m_costs;
    Position  m_position;
    Bar       m_lastBar;
    int64_t   m_nextOrderId = 1;
    int64_t   m_nextTradeId = 1;
    double    m_pendingEntryPrice = 0.0;
    std::string m_pendingEntryDate;
    int64_t   m_pendingEntryBar = 0;
    std::vector<Order> m_pendingOrders;
    std::vector<Order> m_allOrders;
    std::vector<Trade> m_filledTrades;
};

} // namespace qp
