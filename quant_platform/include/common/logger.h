#pragma once

#include <string>
#include <fstream>
#include <mutex>

namespace qp {

enum class LogLevel { Info, Warning, Error };

class Logger {
public:
    static Logger& instance();

    void setLevel(LogLevel level);
    void setLevel(const std::string& levelStr);
    void enableFileOutput(const std::string& filePath);

    void info(const std::string& msg);
    void warn(const std::string& msg);
    void error(const std::string& msg);

private:
    Logger();
    ~Logger();
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;

    void log(LogLevel level, const std::string& msg);
    std::string levelToString(LogLevel level) const;
    std::string timestamp() const;

    LogLevel     m_level = LogLevel::Info;
    std::ofstream m_fileStream;
    std::mutex   m_mutex;
};

} // namespace qp
