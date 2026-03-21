#pragma once

#include <cstdint>
#include <filesystem>
#include <iosfwd>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace e500_ft {

inline constexpr std::size_t kFtRecordWords = 5;
inline constexpr std::size_t kFtRecordBytes = kFtRecordWords * 2;
inline constexpr std::uint8_t kFtStreamVersion = 1;
inline constexpr std::uint64_t kTickNs = 10;

struct CaptureStats {
    std::uint64_t raw_bytes = 0;
    std::uint64_t aligned_bytes = 0;
    std::uint64_t trimmed_bytes = 0;
    std::uint64_t chunks = 0;
};

struct CaptureOptions {
    int device_index = 0;
    int channel = 0;
    std::uint32_t read_timeout_ms = 100;
    std::filesystem::path raw_out;
    std::optional<std::filesystem::path> vcd_out;
    std::optional<double> duration_s = 60.0;
    std::optional<double> idle_timeout_s = std::nullopt;
    std::size_t chunk_size = 1024 * 1024;
    std::optional<std::uint64_t> max_bytes;
};

struct FtAux {
    bool rw = false;
    bool oe = false;
    bool ce1 = false;
    bool ce6 = false;
    bool same_addr = false;
    bool same_data = false;
    bool change_record = false;
    std::uint16_t raw = 0;
};

struct FtKind {
    std::uint8_t raw = 0;

    [[nodiscard]] std::string name() const;
    [[nodiscard]] bool is_known() const;
};

struct FtRecord {
    FtKind kind;
    std::uint32_t delta_ticks = 0;
    std::uint32_t addr = 0;
    std::uint8_t data = 0;
    FtAux aux;
};

class FtStreamVersionError : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};

class CliError : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};

[[nodiscard]] std::string format_capture_start(
    const std::filesystem::path& raw_out,
    const std::optional<std::filesystem::path>& vcd_out,
    const std::optional<double>& duration_s,
    const std::optional<double>& idle_timeout_s,
    const std::optional<std::uint64_t>& max_bytes);

[[nodiscard]] CaptureStats capture_to_vcd(const CaptureOptions& options);

[[nodiscard]] std::vector<FtRecord> read_ft_records(const std::filesystem::path& path);
void write_vcd(const std::vector<FtRecord>& records, std::ostream& out);
void write_vcd_from_capture(const std::filesystem::path& raw_path, const std::filesystem::path& vcd_path);

[[nodiscard]] CaptureOptions parse_capture_args(int argc, char** argv);
void print_capture_help(std::ostream& out, const char* argv0);

struct FtToVcdOptions {
    std::filesystem::path input;
    std::filesystem::path output;
};

[[nodiscard]] FtToVcdOptions parse_ft_to_vcd_args(int argc, char** argv);
void print_ft_to_vcd_help(std::ostream& out, const char* argv0);

}  // namespace e500_ft
