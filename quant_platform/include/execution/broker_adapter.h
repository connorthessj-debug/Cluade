#pragma once

#include "common/data_models.h"
#include <string>

namespace qp {

class IBrokerAdapter {
public:
    virtual ~IBrokerAdapter() = default;
    virtual int64_t submitOrder(const Order& order) = 0;
    virtual bool cancelOrder(int64_t orderId) = 0;
    virtual Position getPosition() const = 0;
    virtual double getAccountBalance() const = 0;
    virtual void onBarUpdate(const Bar& bar) = 0;
    virtual std::string name() const = 0;
};

} // namespace qp
