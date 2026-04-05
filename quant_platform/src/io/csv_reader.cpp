#include "io/csv_reader.h"
#include "common/logger.h"
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <algorithm>

namespace qp {

static std::string trim(const std::string& s) {
    auto start = s.find_first_not_of(" \t\r\n");
    auto end   = s.find_last_not_of(" \t\r\n");
    return (start == std::string::npos) ? "" : s.substr(start, end - start + 1);
}

std::vector<Bar> loadBarsFromCSV(const std::string& path) {
    Logger& log = Logger::instance();
    std::vector<Bar> bars;

    std::ifstream file(path);
    if (!file.is_open()) {
        log.error("Cannot open CSV file: " + path);
        throw std::runtime_error("Cannot open CSV file: " + path);
    }

    std::string line;
    int lineNum = 0;
    bool headerSkipped = false;

    while (std::getline(file, line)) {
        lineNum++;
        std::string trimmed = trim(line);
        if (trimmed.empty()) continue;

        // Skip header if first non-empty line starts with a letter
        if (!headerSkipped) {
            if (!trimmed.empty() && std::isalpha(static_cast<unsigned char>(trimmed[0]))) {
                headerSkipped = true;
                continue;
            }
            headerSkipped = true;
        }

        std::istringstream ss(trimmed);
        std::string token;
        std::vector<std::string> tokens;
        while (std::getline(ss, token, ',')) {
            tokens.push_back(trim(token));
        }

        if (tokens.size() < 5) {
            log.warn("Skipping malformed line " + std::to_string(lineNum) + " in " + path);
            continue;
        }

        Bar bar;
        bar.date  = tokens[0];
        try {
            bar.open  = std::stod(tokens[1]);
            bar.high  = std::stod(tokens[2]);
            bar.low   = std::stod(tokens[3]);
            bar.close = std::stod(tokens[4]);
            if (tokens.size() >= 6) {
                bar.volume = std::stod(tokens[5]);
            }
        } catch (const std::exception& e) {
            log.warn("Skipping line " + std::to_string(lineNum) + ": parse error — " + e.what());
            continue;
        }

        bar.index = static_cast<int64_t>(bars.size());
        bars.push_back(bar);
    }

    log.info("Loaded " + std::to_string(bars.size()) + " bars from " + path);
    return bars;
}

} // namespace qp
