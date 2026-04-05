#pragma once

#include "common/data_models.h"
#include "execution/broker_adapter.h"
#include <vector>
#include <memory>

namespace qp {

class OrderManager {
public:
    explicit OrderManager(std::shared_ptr<IBrokerAdapter> broker);

    int64_t submit(const Order& order);
    bool cancel(int64_t orderId);
    const std::vector<Order>& orderHistory() const { return m_orderHistory; }

private:
    std::shared_ptr<IBrokerAdapter> m_broker;
    std::vector<Order> m_orderHistory;
};

} // namespace qp
