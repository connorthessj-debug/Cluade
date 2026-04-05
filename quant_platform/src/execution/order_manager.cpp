#include "execution/order_manager.h"
#include "common/logger.h"

namespace qp {

OrderManager::OrderManager(std::shared_ptr<IBrokerAdapter> broker)
    : m_broker(std::move(broker))
{}

int64_t OrderManager::submit(const Order& order) {
    int64_t id = m_broker->submitOrder(order);
    Order recorded = order;
    recorded.id = id;
    m_orderHistory.push_back(recorded);
    return id;
}

bool OrderManager::cancel(int64_t orderId) {
    return m_broker->cancelOrder(orderId);
}

} // namespace qp
