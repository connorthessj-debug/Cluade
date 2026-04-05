#include "strategy/strategy_interface.h"
#include "strategy/momentum_strategy.h"
#include "strategy/mean_reversion_strategy.h"

namespace qp {

std::unique_ptr<IStrategy> createStrategy(const std::string& name) {
    if (name == "momentum") {
        return std::make_unique<MomentumStrategy>();
    } else if (name == "mean_reversion") {
        return std::make_unique<MeanReversionStrategy>();
    }
    return nullptr;
}

} // namespace qp
