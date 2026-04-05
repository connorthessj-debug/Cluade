#pragma once

#include "common/data_models.h"
#include <string>

namespace qp {

class ReportWriter {
public:
    static void writeMetricsReport(const std::string& path, const MetricsSummary& metrics);
    static void writeTruthReport(const std::string& path, const TruthReport& report);
    static void writeFullReport(const std::string& path,
                                const BacktestSnapshot& snapshot,
                                const MetricsSummary& metrics,
                                const TruthReport& truth);
};

} // namespace qp
