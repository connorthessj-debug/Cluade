#include "metrics/metric_utils.h"
#include <cmath>
#include <algorithm>

namespace qp {

std::vector<double> dailyReturns(const std::vector<double>& equityCurve) {
    std::vector<double> returns;
    if (equityCurve.size() < 2) return returns;
    returns.reserve(equityCurve.size() - 1);
    for (size_t i = 1; i < equityCurve.size(); i++) {
        if (equityCurve[i - 1] > 0.0) {
            returns.push_back((equityCurve[i] - equityCurve[i - 1]) / equityCurve[i - 1]);
        } else {
            returns.push_back(0.0);
        }
    }
    return returns;
}

double mean(const std::vector<double>& values) {
    if (values.empty()) return 0.0;
    double sum = 0.0;
    for (double v : values) sum += v;
    return sum / static_cast<double>(values.size());
}

double standardDeviation(const std::vector<double>& values) {
    if (values.size() < 2) return 0.0;
    double m = mean(values);
    double sumSq = 0.0;
    for (double v : values) {
        double diff = v - m;
        sumSq += diff * diff;
    }
    return std::sqrt(sumSq / static_cast<double>(values.size() - 1));
}

double downsideDeviation(const std::vector<double>& returns, double threshold) {
    if (returns.empty()) return 0.0;
    double sumSq = 0.0;
    int count = 0;
    for (double r : returns) {
        if (r < threshold) {
            double diff = r - threshold;
            sumSq += diff * diff;
            count++;
        }
    }
    if (count == 0) return 0.0;
    return std::sqrt(sumSq / static_cast<double>(count));
}

DrawdownInfo maxDrawdown(const std::vector<double>& equityCurve) {
    DrawdownInfo info;
    if (equityCurve.empty()) return info;

    double peak = equityCurve[0];
    int peakIdx = 0;
    double worstDD = 0.0;
    int worstStart = 0;
    int worstEnd = 0;

    for (size_t i = 1; i < equityCurve.size(); i++) {
        if (equityCurve[i] > peak) {
            peak = equityCurve[i];
            peakIdx = static_cast<int>(i);
        }
        double dd = (peak > 0.0) ? (peak - equityCurve[i]) / peak : 0.0;
        if (dd > worstDD) {
            worstDD = dd;
            worstStart = peakIdx;
            worstEnd = static_cast<int>(i);
        }
    }

    info.maxDrawdown = worstDD;
    info.maxDDStartIdx = worstStart;
    info.maxDDEndIdx = worstEnd;
    info.maxDDDuration = worstEnd - worstStart;
    return info;
}

} // namespace qp
