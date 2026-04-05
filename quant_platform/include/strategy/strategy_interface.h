#pragma once

#include "common/data_models.h"
#include <vector>
#include <string>
#include <memory>

namespace qp {

struct StrategyContext {
    Position     currentPosition;
    double       equity          = 0.0;
    double       cash            = 0.0;
    int64_t      barIndex        = 0;
    const Bar*   currentBar      = nullptr;
    const std::vector<Bar>* bars = nullptr;
};

class IStrategy {
public:
    virtual ~IStrategy() = default;
    virtual std::string name() const = 0;
    virtual void init(const StrategyParams& params) = 0;
    virtual std::vector<Order> onBar(const Bar& bar, const StrategyContext& ctx) = 0;
    virtual void onOrderFilled(const Trade& trade) = 0;
    virtual int requiredWarmupBars() const = 0;
    virtual void reset() = 0;
};

std::unique_ptr<IStrategy> createStrategy(const std::string& name);

} // namespace qp
