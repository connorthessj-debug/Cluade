#include "common/config_loader.h"
#include "common/logger.h"
#include "common/json.hpp"
#include <fstream>
#include <stdexcept>

namespace qp {

AppConfig loadAppConfig(const std::string& path) {
    Logger& log = Logger::instance();
    AppConfig config;

    std::ifstream file(path);
    if (!file.is_open()) {
        log.warn("Config file not found: " + path + " — using defaults");
        return config;
    }

    nlohmann::json j;
    try {
        file >> j;
    } catch (const nlohmann::json::parse_error& e) {
        log.error("Failed to parse config: " + std::string(e.what()));
        throw std::runtime_error("Invalid config file: " + path);
    }

    if (j.contains("dataPath"))           config.dataPath        = j["dataPath"].get<std::string>();
    if (j.contains("defaultStrategy"))    config.defaultStrategy = j["defaultStrategy"].get<std::string>();
    if (j.contains("initialCapital"))     config.initialCapital  = j["initialCapital"].get<double>();
    if (j.contains("logLevel"))           config.logLevel        = j["logLevel"].get<std::string>();
    if (j.contains("configDir"))          config.configDir       = j["configDir"].get<std::string>();
    if (j.contains("outputDir"))          config.outputDir       = j["outputDir"].get<std::string>();
    if (j.contains("monteCarloSims"))     config.monteCarloSims  = j["monteCarloSims"].get<int>();
    if (j.contains("riskFreeRate"))       config.riskFreeRate    = j["riskFreeRate"].get<double>();
    if (j.contains("tradingDaysPerYear")) config.tradingDaysPerYear = j["tradingDaysPerYear"].get<int>();

    if (j.contains("costs")) {
        auto& c = j["costs"];
        if (c.contains("commissionRate")) config.costs.commissionRate = c["commissionRate"].get<double>();
        if (c.contains("slippageFactor")) config.costs.slippageFactor = c["slippageFactor"].get<double>();
        if (c.contains("spreadFactor"))   config.costs.spreadFactor   = c["spreadFactor"].get<double>();
    }

    log.info("Loaded config from: " + path);
    return config;
}

} // namespace qp
