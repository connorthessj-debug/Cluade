#include "common/logger.h"
#include <iostream>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <algorithm>

namespace qp {

Logger& Logger::instance() {
    static Logger inst;
    return inst;
}

Logger::Logger() = default;

Logger::~Logger() {
    if (m_fileStream.is_open()) {
        m_fileStream.close();
    }
}

void Logger::setLevel(LogLevel level) {
    m_level = level;
}

void Logger::setLevel(const std::string& levelStr) {
    std::string lower = levelStr;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (lower == "info")         m_level = LogLevel::Info;
    else if (lower == "warning") m_level = LogLevel::Warning;
    else if (lower == "error")   m_level = LogLevel::Error;
}

void Logger::enableFileOutput(const std::string& filePath) {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_fileStream.is_open()) {
        m_fileStream.close();
    }
    m_fileStream.open(filePath, std::ios::app);
}

void Logger::info(const std::string& msg)  { log(LogLevel::Info, msg); }
void Logger::warn(const std::string& msg)  { log(LogLevel::Warning, msg); }
void Logger::error(const std::string& msg) { log(LogLevel::Error, msg); }

void Logger::log(LogLevel level, const std::string& msg) {
    if (level < m_level) return;

    std::lock_guard<std::mutex> lock(m_mutex);
    std::string line = "[" + timestamp() + "] [" + levelToString(level) + "] " + msg;
    std::cout << line << std::endl;

    if (m_fileStream.is_open()) {
        m_fileStream << line << std::endl;
    }
}

std::string Logger::levelToString(LogLevel level) const {
    switch (level) {
        case LogLevel::Info:    return "INFO";
        case LogLevel::Warning: return "WARN";
        case LogLevel::Error:   return "ERROR";
    }
    return "UNKNOWN";
}

std::string Logger::timestamp() const {
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buf;
#ifdef _WIN32
    localtime_s(&tm_buf, &time);
#else
    localtime_r(&time, &tm_buf);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y-%m-%d %H:%M:%S");
    return oss.str();
}

} // namespace qp
