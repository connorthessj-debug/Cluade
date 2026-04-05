#pragma once

#include "common/data_models.h"
#include <vector>

namespace qp {

class PositionTracker {
public:
    void reset(double initialCapital);
    void processFill(const Trade& fill);
    void markToMarket(double currentPrice);

    Position currentPosition() const;
    double equity() const;
    double cash() const;
    const std::vector<double>& equityCurve() const;
    const std::vector<Trade>& completedTrades() const;

private:
    Position m_position;
    double   m_cash     = 0.0;
    double   m_equity   = 0.0;
    std::vector<double> m_equityCurve;
    std::vector<Trade>  m_completedTrades;

    // Pending entry for matching
    double  m_pendingEntryPrice   = 0.0;
    int64_t m_pendingEntryBar     = 0;
    std::string m_pendingEntryDate;
};

} // namespace qp
