#pragma once

#include "optimization/optimizer_interface.h"

namespace qp {

class RandomOptimizer : public IOptimizer {
public:
    explicit RandomOptimizer(int maxIterations = 500, unsigned int seed = 0);

    OptimizationResult optimize(
        const std::vector<Bar>& bars,
        IStrategy& strategy,
        const std::vector<ParamRange>& ranges,
        ObjectiveFunction objective,
        const AppConfig& config) override;

    std::string name() const override { return "random"; }

private:
    int m_maxIterations;
    unsigned int m_seed;
};

} // namespace qp
