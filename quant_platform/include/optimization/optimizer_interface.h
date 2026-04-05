#pragma once

#include "common/data_models.h"
#include "strategy/strategy_interface.h"
#include <vector>
#include <string>
#include <functional>

namespace qp {

struct ParamRange {
    std::string name;
    double min  = 0.0;
    double max  = 1.0;
    double step = 0.1;
};

enum class ObjectiveFunction {
    Sharpe,
    Sortino,
    TotalReturn,
    ProfitFactor,
    Expectancy
};

ObjectiveFunction parseObjective(const std::string& name);
double scoreByObjective(const MetricsSummary& metrics, ObjectiveFunction obj);

class IOptimizer {
public:
    virtual ~IOptimizer() = default;
    virtual OptimizationResult optimize(
        const std::vector<Bar>& bars,
        IStrategy& strategy,
        const std::vector<ParamRange>& ranges,
        ObjectiveFunction objective,
        const AppConfig& config) = 0;

    virtual std::string name() const = 0;
};

} // namespace qp
