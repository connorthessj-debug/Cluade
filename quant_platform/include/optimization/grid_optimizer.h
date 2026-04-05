#pragma once

#include "optimization/optimizer_interface.h"

namespace qp {

class GridOptimizer : public IOptimizer {
public:
    OptimizationResult optimize(
        const std::vector<Bar>& bars,
        IStrategy& strategy,
        const std::vector<ParamRange>& ranges,
        ObjectiveFunction objective,
        const AppConfig& config) override;

    std::string name() const override { return "grid"; }
};

} // namespace qp
