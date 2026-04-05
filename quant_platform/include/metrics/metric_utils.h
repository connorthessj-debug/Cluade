#pragma once

#include <vector>

namespace qp {

struct DrawdownInfo {
    double maxDrawdown     = 0.0;
    int    maxDDStartIdx   = 0;
    int    maxDDEndIdx     = 0;
    int    maxDDDuration   = 0;
};

std::vector<double> dailyReturns(const std::vector<double>& equityCurve);
double standardDeviation(const std::vector<double>& values);
double downsideDeviation(const std::vector<double>& returns, double threshold = 0.0);
DrawdownInfo maxDrawdown(const std::vector<double>& equityCurve);
double mean(const std::vector<double>& values);

} // namespace qp
