#pragma once

#include "common/data_models.h"
#include "strategy/strategy_interface.h"
#include "optimization/optimizer_interface.h"
#include <vector>
#include <string>

namespace qp {

struct WalkForwardConfig {
    std::string windowType    = "rolling"; // "rolling" or "anchored"
    int         numWindows    = 5;
    double      inSampleRatio = 0.7;
    std::string objective     = "sharpe";
};

WalkForwardConfig loadWalkForwardConfig(const std::string& path);

class WalkForwardEngine {
public:
    WalkForwardReport run(
        const std::vector<Bar>& bars,
        IStrategy& strategy,
        const std::vector<ParamRange>& ranges,
        const WalkForwardConfig& wfConfig,
        const AppConfig& appConfig);
};

} // namespace qp
