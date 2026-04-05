#pragma once

#include "common/data_models.h"
#include <string>
#include <vector>

namespace qp {

std::vector<Bar> loadBarsFromCSV(const std::string& path);

} // namespace qp
