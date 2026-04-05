#include "montecarlo/monte_carlo_engine.h"
#include "common/logger.h"
#include <algorithm>
#include <random>
#include <numeric>
#include <cmath>

namespace qp {

double MonteCarloEngine::computePercentile(std::vector<double>& sorted, double pct) const {
    if (sorted.empty()) return 0.0;
    std::sort(sorted.begin(), sorted.end());
    double idx = pct * static_cast<double>(sorted.size() - 1);
    size_t lo = static_cast<size_t>(std::floor(idx));
    size_t hi = static_cast<size_t>(std::ceil(idx));
    if (lo == hi || hi >= sorted.size()) return sorted[lo];
    double frac = idx - static_cast<double>(lo);
    return sorted[lo] * (1.0 - frac) + sorted[hi] * frac;
}

MonteCarloEngine::MCDrawdownInfo MonteCarloEngine::computeMaxDD(const std::vector<double>& equityCurve) const {
    MCDrawdownInfo info;
    double peak = equityCurve.empty() ? 0.0 : equityCurve[0];
    for (double eq : equityCurve) {
        if (eq > peak) peak = eq;
        double dd = (peak > 0.0) ? (peak - eq) / peak : 0.0;
        if (dd > info.maxDD) info.maxDD = dd;
    }
    return info;
}

MonteCarloSummary MonteCarloEngine::run(const std::vector<Trade>& trades,
                                         double initialCapital,
                                         int numSimulations,
                                         unsigned int seed) {
    Logger::instance().info("Running Monte Carlo (reshuffle): " +
                            std::to_string(numSimulations) + " sims");

    MonteCarloSummary summary;
    summary.numSimulations = numSimulations;
    summary.mode = "reshuffle";

    if (trades.empty()) return summary;

    std::mt19937 rng(seed == 0 ? std::random_device{}() : seed);
    std::vector<double> pnls;
    pnls.reserve(trades.size());
    for (const auto& t : trades) pnls.push_back(t.pnl);

    std::vector<double> finalEquities;
    std::vector<double> maxDDs;
    finalEquities.reserve(static_cast<size_t>(numSimulations));
    maxDDs.reserve(static_cast<size_t>(numSimulations));
    int failures = 0;

    for (int sim = 0; sim < numSimulations; sim++) {
        std::shuffle(pnls.begin(), pnls.end(), rng);

        std::vector<double> equity;
        equity.reserve(pnls.size() + 1);
        equity.push_back(initialCapital);
        double current = initialCapital;
        for (double pnl : pnls) {
            current += pnl;
            equity.push_back(current);
        }

        finalEquities.push_back(current);
        auto ddInfo = computeMaxDD(equity);
        maxDDs.push_back(ddInfo.maxDD);
        if (current < initialCapital) failures++;
    }

    summary.p5FinalEquity = computePercentile(finalEquities, 0.05);
    summary.p25FinalEquity = computePercentile(finalEquities, 0.25);
    summary.medianFinalEquity = computePercentile(finalEquities, 0.50);
    summary.p75FinalEquity = computePercentile(finalEquities, 0.75);
    summary.p95FinalEquity = computePercentile(finalEquities, 0.95);
    summary.failureRate = static_cast<double>(failures) / static_cast<double>(numSimulations);
    summary.worstDrawdown = *std::max_element(maxDDs.begin(), maxDDs.end());
    summary.medianDrawdown = computePercentile(maxDDs, 0.50);

    return summary;
}

MonteCarloSummary MonteCarloEngine::runSlippagePerturbation(
    const std::vector<Trade>& trades,
    double initialCapital,
    int numSimulations,
    double slippageNoiseStdDev,
    unsigned int seed) {

    Logger::instance().info("Running Monte Carlo (slippage perturbation)");

    MonteCarloSummary summary;
    summary.numSimulations = numSimulations;
    summary.mode = "slippage";

    if (trades.empty()) return summary;

    std::mt19937 rng(seed == 0 ? std::random_device{}() : seed);
    std::normal_distribution<double> noiseDist(0.0, slippageNoiseStdDev);

    std::vector<double> finalEquities;
    int failures = 0;

    for (int sim = 0; sim < numSimulations; sim++) {
        double current = initialCapital;
        for (const auto& t : trades) {
            double noiseFactor = 1.0 + noiseDist(rng);
            double adjustedPnl = t.pnl * noiseFactor;
            current += adjustedPnl;
        }
        finalEquities.push_back(current);
        if (current < initialCapital) failures++;
    }

    summary.p5FinalEquity = computePercentile(finalEquities, 0.05);
    summary.p25FinalEquity = computePercentile(finalEquities, 0.25);
    summary.medianFinalEquity = computePercentile(finalEquities, 0.50);
    summary.p75FinalEquity = computePercentile(finalEquities, 0.75);
    summary.p95FinalEquity = computePercentile(finalEquities, 0.95);
    summary.failureRate = static_cast<double>(failures) / static_cast<double>(numSimulations);

    return summary;
}

MonteCarloSummary MonteCarloEngine::runMissedTrades(
    const std::vector<Trade>& trades,
    double initialCapital,
    int numSimulations,
    double missedRate,
    unsigned int seed) {

    Logger::instance().info("Running Monte Carlo (missed trades, rate=" +
                            std::to_string(missedRate) + ")");

    MonteCarloSummary summary;
    summary.numSimulations = numSimulations;
    summary.mode = "missed";

    if (trades.empty()) return summary;

    std::mt19937 rng(seed == 0 ? std::random_device{}() : seed);
    std::uniform_real_distribution<double> uniformDist(0.0, 1.0);

    std::vector<double> finalEquities;
    int failures = 0;

    for (int sim = 0; sim < numSimulations; sim++) {
        double current = initialCapital;
        for (const auto& t : trades) {
            if (uniformDist(rng) > missedRate) {
                current += t.pnl;
            }
        }
        finalEquities.push_back(current);
        if (current < initialCapital) failures++;
    }

    summary.p5FinalEquity = computePercentile(finalEquities, 0.05);
    summary.p25FinalEquity = computePercentile(finalEquities, 0.25);
    summary.medianFinalEquity = computePercentile(finalEquities, 0.50);
    summary.p75FinalEquity = computePercentile(finalEquities, 0.75);
    summary.p95FinalEquity = computePercentile(finalEquities, 0.95);
    summary.failureRate = static_cast<double>(failures) / static_cast<double>(numSimulations);

    return summary;
}

} // namespace qp
