#include "e500_ft_host.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <string_view>
#include <system_error>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>
#include <memory>

#if defined(__APPLE__)
#include <mach-o/dyld.h>
#elif defined(__linux__)
#include <unistd.h>
#endif

namespace e500_ft {

namespace {

using FtStatus = unsigned long;
using FtHandle = void*;
using FtUchar = unsigned char;
using FtUlong = unsigned long;
using FtDword = unsigned long;

constexpr FtStatus kFtOk = 0;
constexpr FtStatus kFtTimeout = 19;
constexpr FtDword kFtOpenByIndex = 0x00000010;

constexpr std::uint32_t kFtKindShift = 72;
constexpr std::uint32_t kFtDeltaShift = 40;
constexpr std::uint32_t kFtAddrShift = 22;
constexpr std::uint32_t kFtDataShift = 14;
constexpr std::uint16_t kFtAuxMask = 0x3FFF;
constexpr std::uint32_t kFtAddrMask = 0x3FFFF;
constexpr std::uint8_t kFtDataMask = 0xFF;

constexpr std::uint8_t kFtKindBusChange = 0x00;
constexpr std::uint8_t kFtKindCe1Read = 0x01;
constexpr std::uint8_t kFtKindCe1Write = 0x02;
constexpr std::uint8_t kFtKindCe6Read = 0x03;
constexpr std::uint8_t kFtKindCe6WriteAttempt = 0x04;
constexpr std::uint8_t kFtKindSync = 0xF0;
constexpr std::uint8_t kFtKindOverflow = 0xF1;
constexpr std::uint8_t kFtKindConfig = 0xF2;

std::filesystem::path executable_path() {
#if defined(__APPLE__)
    std::uint32_t size = 0;
    _NSGetExecutablePath(nullptr, &size);
    std::string buffer(size, '\0');
    if (_NSGetExecutablePath(buffer.data(), &size) != 0) {
        throw std::runtime_error("failed to determine executable path");
    }
    return std::filesystem::weakly_canonical(std::filesystem::path(buffer.c_str()));
#elif defined(__linux__)
    std::vector<char> buffer(4096);
    const auto read = ::readlink("/proc/self/exe", buffer.data(), buffer.size() - 1);
    if (read <= 0) {
        throw std::runtime_error("failed to determine executable path");
    }
    buffer[static_cast<std::size_t>(read)] = '\0';
    return std::filesystem::weakly_canonical(std::filesystem::path(buffer.data()));
#else
    throw std::runtime_error("unsupported platform for executable path discovery");
#endif
}

std::filesystem::path find_repo_root() {
    if (const char* env = std::getenv("RETROBUS_REPO_ROOT")) {
        return std::filesystem::path(env);
    }

    const auto exe = executable_path();
    for (auto parent = exe.parent_path(); !parent.empty(); parent = parent.parent_path()) {
        if (std::filesystem::exists(parent / "py" / "d3xx") &&
            std::filesystem::exists(parent / "gateware" / "reference")) {
            return parent;
        }
    }
    throw std::runtime_error("failed to locate retrobus-explorer repo root");
}

std::string format_double_g(const double value) {
    std::ostringstream out;
    out << std::defaultfloat << value;
    return out.str();
}

[[nodiscard]] std::uint16_t read_u16_le(const std::byte* bytes) {
    return static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[0])) |
           (static_cast<std::uint16_t>(std::to_integer<std::uint8_t>(bytes[1])) << 8);
}

FtAux decode_ft_aux(const std::uint16_t raw) {
    return FtAux{
        .rw = (raw & (1u << 0)) != 0,
        .oe = (raw & (1u << 1)) != 0,
        .ce1 = (raw & (1u << 2)) != 0,
        .ce6 = (raw & (1u << 3)) != 0,
        .same_addr = (raw & (1u << 4)) != 0,
        .same_data = (raw & (1u << 5)) != 0,
        .change_record = (raw & (1u << 6)) != 0,
        .raw = static_cast<std::uint16_t>(raw & kFtAuxMask),
    };
}

FtRecord decode_ft_record(const std::array<std::byte, kFtRecordBytes>& bytes) {
    __uint128_t raw = 0;
    for (std::size_t idx = 0; idx < kFtRecordWords; ++idx) {
        const auto word = read_u16_le(bytes.data() + (idx * 2));
        raw |= (static_cast<__uint128_t>(word) << (16 * idx));
    }

    const auto kind = static_cast<std::uint8_t>((raw >> kFtKindShift) & 0xFFu);
    const auto delta_ticks = static_cast<std::uint32_t>((raw >> kFtDeltaShift) & 0xFFFFFFFFu);
    const auto addr = static_cast<std::uint32_t>((raw >> kFtAddrShift) & kFtAddrMask);
    const auto data = static_cast<std::uint8_t>((raw >> kFtDataShift) & kFtDataMask);
    const auto aux_raw = static_cast<std::uint16_t>(raw & kFtAuxMask);

    return FtRecord{
        .kind = FtKind{kind},
        .delta_ticks = delta_ticks,
        .addr = addr,
        .data = data,
        .aux = decode_ft_aux(aux_raw),
    };
}

std::vector<FtRecord> decode_ft_records(const std::vector<std::byte>& bytes) {
    if ((bytes.size() % 2) != 0) {
        throw std::runtime_error("expected even number of bytes at end of FT stream");
    }
    if ((bytes.size() % kFtRecordBytes) != 0) {
        const auto trailing_words = (bytes.size() % kFtRecordBytes) / 2;
        throw std::runtime_error("incomplete FT record: got " + std::to_string(trailing_words) + " trailing words");
    }

    std::vector<FtRecord> records;
    records.reserve(bytes.size() / kFtRecordBytes);
    for (std::size_t offset = 0; offset < bytes.size(); offset += kFtRecordBytes) {
        std::array<std::byte, kFtRecordBytes> chunk{};
        std::memcpy(chunk.data(), bytes.data() + offset, kFtRecordBytes);
        records.push_back(decode_ft_record(chunk));
    }
    return records;
}

void validate_ft_records(const std::vector<FtRecord>& records) {
    if (records.empty()) {
        throw FtStreamVersionError("empty FT capture");
    }
    if (records.front().kind.raw != kFtKindSync) {
        throw FtStreamVersionError(
            "expected first FT record to be SYNC, got " + records.front().kind.name());
    }
    if (records.front().data != kFtStreamVersion) {
        throw FtStreamVersionError(
            "unsupported FT stream version " + std::to_string(records.front().data) +
            ", expected " + std::to_string(kFtStreamVersion));
    }
}

std::vector<std::byte> read_file_bytes(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("failed to open " + path.string());
    }

    in.seekg(0, std::ios::end);
    const auto size = static_cast<std::size_t>(in.tellg());
    in.seekg(0, std::ios::beg);

    std::vector<std::byte> bytes(size);
    if (size > 0) {
        in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(size));
        if (!in) {
            throw std::runtime_error("failed to read " + path.string());
        }
    }
    return bytes;
}

struct Signal {
    char ident = '\0';
    std::size_t width = 1;
    std::string name;
};

class VcdWriter {
  public:
    explicit VcdWriter(std::ostream& out, std::string timescale = "1ns")
        : out_(out), timescale_(std::move(timescale)) {}

    void add_signal(const std::string& name, const std::size_t width = 1) {
        if (signals_by_name_.contains(name)) {
            throw std::runtime_error("duplicate VCD signal " + name);
        }
        const auto ident = static_cast<char>(next_id_++);
        signals_.push_back(Signal{ident, width, name});
        signals_by_name_.emplace(name, signals_.back());
    }

    void header() {
        if (started_) {
            return;
        }
        started_ = true;
        emit("$date");
        emit("  generated by ft_to_vcd.py");
        emit("$end");
        emit("$version");
        emit("  e500 ft decoder");
        emit("$end");
        emit("$timescale " + timescale_ + " $end");
        emit("$scope module e500_ft $end");
        for (const auto& signal : signals_) {
            emit("$var wire " + std::to_string(signal.width) + " " + std::string(1, signal.ident) + " " +
                 signal.name + " $end");
        }
        emit("$upscope $end");
        emit("$enddefinitions $end");
    }

    void change(const std::uint64_t time_ns, const std::string& signal_name, const std::uint64_t value) {
        if (!started_) {
            header();
        }
        const auto it = signals_by_name_.find(signal_name);
        if (it == signals_by_name_.end()) {
            throw std::runtime_error("unknown VCD signal " + signal_name);
        }
        if (last_time_.has_value() && time_ns < *last_time_) {
            throw std::runtime_error(
                "VCD time must be monotonic (time_ns=" + std::to_string(time_ns) +
                ", last_time_ns=" + std::to_string(*last_time_) + ")");
        }
        if (!last_time_.has_value() || time_ns != *last_time_) {
            emit("#" + std::to_string(time_ns));
            last_time_ = time_ns;
        }
        const auto& signal = it->second;
        if (signal.width == 1) {
            emit(std::string(1, value ? '1' : '0') + signal.ident);
        } else {
            emit("b" + binary_string(value, signal.width) + " " + signal.ident);
        }
    }

  private:
    void emit(const std::string& line) {
        out_ << line << '\n';
    }

    static std::string binary_string(const std::uint64_t value, const std::size_t width) {
        std::string out(width, '0');
        for (std::size_t idx = 0; idx < width; ++idx) {
            const auto shift = width - idx - 1;
            out[idx] = ((value >> shift) & 1u) != 0 ? '1' : '0';
        }
        return out;
    }

    std::ostream& out_;
    std::string timescale_;
    std::vector<Signal> signals_;
    std::unordered_map<std::string, Signal> signals_by_name_;
    int next_id_ = 33;
    bool started_ = false;
    std::optional<std::uint64_t> last_time_;
};

const std::array<std::pair<std::string_view, std::size_t>, 24> kSignals{{
    {"meta_ft_enabled", 1},
    {"meta_stream_version", 8},
    {"meta_kind", 8},
    {"meta_delta_ticks", 32},
    {"meta_classify_delay_ticks", 18},
    {"meta_overflow_count", 26},
    {"bus_addr", 18},
    {"bus_data", 8},
    {"bus_rw", 1},
    {"bus_oe", 1},
    {"bus_ce1", 1},
    {"bus_ce6", 1},
    {"bus_same_addr", 1},
    {"bus_same_data", 1},
    {"bus_change_record", 1},
    {"event_bus_change", 1},
    {"event_idle_change", 1},
    {"event_ce1_read", 1},
    {"event_ce1_write", 1},
    {"event_ce6_read", 1},
    {"event_ce6_write_attempt", 1},
    {"event_sync", 1},
    {"event_config", 1},
    {"event_overflow", 1},
}};

const std::array<std::string_view, 9> kPulseNames{{
    "event_bus_change",
    "event_idle_change",
    "event_ce1_read",
    "event_ce1_write",
    "event_ce6_read",
    "event_ce6_write_attempt",
    "event_sync",
    "event_config",
    "event_overflow",
}};

std::vector<std::string_view> write_record_group(
    const std::uint64_t time_ns,
    const std::vector<const FtRecord*>& records,
    VcdWriter& writer) {
    std::unordered_map<std::string_view, std::uint64_t> active_pulses;
    for (const auto pulse : kPulseNames) {
        active_pulses.emplace(pulse, 0);
    }

    for (const auto* record : records) {
        writer.change(time_ns, "meta_kind", record->kind.raw);
        writer.change(time_ns, "meta_delta_ticks", record->delta_ticks);
        writer.change(time_ns, "bus_addr", record->addr);
        writer.change(time_ns, "bus_data", record->data);
        writer.change(time_ns, "bus_rw", record->aux.rw ? 1 : 0);
        writer.change(time_ns, "bus_oe", record->aux.oe ? 1 : 0);
        writer.change(time_ns, "bus_ce1", record->aux.ce1 ? 1 : 0);
        writer.change(time_ns, "bus_ce6", record->aux.ce6 ? 1 : 0);
        writer.change(time_ns, "bus_same_addr", record->aux.same_addr ? 1 : 0);
        writer.change(time_ns, "bus_same_data", record->aux.same_data ? 1 : 0);
        writer.change(time_ns, "bus_change_record", record->aux.change_record ? 1 : 0);

        if (record->kind.raw == kFtKindSync) {
            writer.change(time_ns, "meta_stream_version", record->data);
            active_pulses["event_sync"] = 1;
        } else if (record->kind.raw == kFtKindConfig) {
            writer.change(time_ns, "meta_classify_delay_ticks", record->addr);
            writer.change(time_ns, "meta_ft_enabled", (record->aux.raw & 0x1u) != 0 ? 1 : 0);
            active_pulses["event_config"] = 1;
        } else if (record->kind.raw == kFtKindOverflow) {
            const auto overflow_count =
                static_cast<std::uint64_t>(record->addr) | (static_cast<std::uint64_t>(record->data) << 18);
            writer.change(time_ns, "meta_overflow_count", overflow_count);
            active_pulses["event_overflow"] = 1;
        } else {
            active_pulses["event_bus_change"] = 1;
            if (record->kind.raw == kFtKindBusChange) {
                active_pulses["event_idle_change"] = 1;
            } else if (record->kind.raw == kFtKindCe1Read) {
                active_pulses["event_ce1_read"] = 1;
            } else if (record->kind.raw == kFtKindCe1Write) {
                active_pulses["event_ce1_write"] = 1;
            } else if (record->kind.raw == kFtKindCe6Read) {
                active_pulses["event_ce6_read"] = 1;
            } else if (record->kind.raw == kFtKindCe6WriteAttempt) {
                active_pulses["event_ce6_write_attempt"] = 1;
            }
        }
    }

    std::vector<std::string_view> active_names;
    for (const auto pulse : kPulseNames) {
        writer.change(time_ns, std::string(pulse), active_pulses[pulse]);
        if (active_pulses[pulse] != 0) {
            active_names.push_back(pulse);
        }
    }
    return active_names;
}

void write_vcd_records(const std::vector<FtRecord>& records, std::ostream& out) {
    validate_ft_records(records);
    VcdWriter writer(out);
    for (const auto& [name, width] : kSignals) {
        writer.add_signal(std::string(name), width);
    }
    writer.header();

    for (const auto& [name, width] : kSignals) {
        (void)width;
        writer.change(0, std::string(name), 0);
    }

    std::vector<std::string_view> active_pulses;
    std::optional<std::uint64_t> last_time_ns;
    std::uint64_t tick = 0;
    std::size_t index = 0;
    while (index < records.size()) {
        tick += records[index].delta_ticks;
        const auto time_ns = tick * kTickNs;

        std::vector<const FtRecord*> group;
        group.push_back(&records[index]);
        ++index;

        while (index < records.size() && records[index].delta_ticks == 0) {
            group.push_back(&records[index]);
            ++index;
        }

        for (const auto pulse : active_pulses) {
            writer.change(time_ns, std::string(pulse), 0);
        }
        active_pulses = write_record_group(time_ns, group, writer);
        last_time_ns = time_ns;
    }

    if (last_time_ns.has_value()) {
        for (const auto pulse : active_pulses) {
            writer.change(*last_time_ns + kTickNs, std::string(pulse), 0);
        }
    }
}

class D3xxLibrary {
  public:
    D3xxLibrary() {
        const auto repo_root = find_repo_root();
#if defined(__APPLE__)
        const auto lib_path = repo_root / "py" / "d3xx" / "libftd3xx.dylib";
#else
        const auto lib_path = repo_root / "py" / "d3xx" / "libftd3xx.so";
#endif
        handle_ = ::dlopen(lib_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (handle_ == nullptr) {
            throw std::runtime_error("failed to load D3XX library from " + lib_path.string() + ": " + ::dlerror());
        }

        load(create_, "FT_Create");
        load(close_, "FT_Close");
        load(read_pipe_ex_, "FT_ReadPipeEx");
    }

    ~D3xxLibrary() {
        if (handle_ != nullptr) {
            ::dlclose(handle_);
        }
    }

    D3xxLibrary(const D3xxLibrary&) = delete;
    D3xxLibrary& operator=(const D3xxLibrary&) = delete;

    FtStatus create(void* arg, const FtDword flags, FtHandle* out) const {
        return create_(arg, flags, out);
    }

    FtStatus close(const FtHandle handle) const {
        return close_(handle);
    }

    FtStatus read_pipe_ex(
        const FtHandle handle,
        const FtUchar pipe_id,
        void* buffer,
        const FtUlong buffer_length,
        FtUlong* bytes_transferred,
        const FtUlong timeout_ms) const {
        return read_pipe_ex_(handle, pipe_id, buffer, buffer_length, bytes_transferred, timeout_ms);
    }

  private:
    template <typename Fn>
    void load(Fn& slot, const char* symbol) {
        void* sym = ::dlsym(handle_, symbol);
        if (sym == nullptr) {
            throw std::runtime_error("failed to resolve D3XX symbol " + std::string(symbol));
        }
        slot = reinterpret_cast<Fn>(sym);
    }

    void* handle_ = nullptr;
    FtStatus (*create_)(void*, FtDword, FtHandle*) = nullptr;
    FtStatus (*close_)(FtHandle) = nullptr;
    FtStatus (*read_pipe_ex_)(FtHandle, FtUchar, void*, FtUlong, FtUlong*, FtUlong) = nullptr;
};

class D3xxDevice {
  public:
    D3xxDevice(const int device_index, const int channel, const std::uint32_t timeout_ms)
        : library_(std::make_shared<D3xxLibrary>()),
          channel_(static_cast<FtUchar>(channel)),
          timeout_ms_(timeout_ms) {
        FtHandle handle = nullptr;
        const auto status = library_->create(reinterpret_cast<void*>(static_cast<std::uintptr_t>(device_index)),
                                             kFtOpenByIndex, &handle);
        if (status != kFtOk || handle == nullptr) {
            throw std::runtime_error("failed to open FT600 device via D3XX");
        }
        handle_ = handle;
    }

    ~D3xxDevice() {
        if (handle_ != nullptr) {
            library_->close(handle_);
        }
    }

    std::size_t read(std::byte* buffer, const std::size_t size) const {
        FtUlong bytes_transferred = 0;
        const auto status = library_->read_pipe_ex(
            handle_, channel_, buffer, static_cast<FtUlong>(size), &bytes_transferred, timeout_ms_);
        if (status == kFtOk || status == kFtTimeout) {
            return static_cast<std::size_t>(bytes_transferred);
        }
        throw std::runtime_error("FT_ReadPipeEx failed with status " + std::to_string(status));
    }

  private:
    std::shared_ptr<D3xxLibrary> library_;
    FtHandle handle_ = nullptr;
    FtUchar channel_ = 0;
    FtUlong timeout_ms_ = 0;
};

CaptureStats truncate_to_ft_records(const std::filesystem::path& path, const std::uint64_t raw_bytes,
                                   const std::uint64_t chunks) {
    const auto aligned_bytes = raw_bytes - (raw_bytes % kFtRecordBytes);
    const auto trimmed_bytes = raw_bytes - aligned_bytes;
    if (trimmed_bytes != 0) {
        std::filesystem::resize_file(path, aligned_bytes);
    }
    return CaptureStats{
        .raw_bytes = raw_bytes,
        .aligned_bytes = aligned_bytes,
        .trimmed_bytes = trimmed_bytes,
        .chunks = chunks,
    };
}

CaptureStats capture_stream(const CaptureOptions& options) {
    if (!options.duration_s.has_value() && !options.idle_timeout_s.has_value() && !options.max_bytes.has_value()) {
        throw std::runtime_error("capture needs at least one stop condition");
    }

    D3xxDevice device(options.device_index, options.channel, options.read_timeout_ms);
    std::vector<std::byte> buffer(options.chunk_size);

    std::ofstream out(options.raw_out, std::ios::binary | std::ios::trunc);
    if (!out) {
        throw std::runtime_error("failed to open " + options.raw_out.string());
    }

    std::uint64_t raw_bytes = 0;
    std::uint64_t chunks = 0;
    const auto started_at = std::chrono::steady_clock::now();
    auto last_data_at = started_at;

    while (true) {
        const auto now = std::chrono::steady_clock::now();
        const auto elapsed_s = std::chrono::duration<double>(now - started_at).count();
        if (options.duration_s.has_value() && elapsed_s >= *options.duration_s) {
            break;
        }
        if (options.max_bytes.has_value() && raw_bytes >= *options.max_bytes) {
            break;
        }

        auto bytes_read = device.read(buffer.data(), buffer.size());
        if (bytes_read != 0) {
            if (options.max_bytes.has_value()) {
                const auto remaining = *options.max_bytes - raw_bytes;
                if (remaining == 0) {
                    break;
                }
                bytes_read = std::min<std::size_t>(bytes_read, static_cast<std::size_t>(remaining));
            }
            out.write(reinterpret_cast<const char*>(buffer.data()), static_cast<std::streamsize>(bytes_read));
            if (!out) {
                throw std::runtime_error("failed to write " + options.raw_out.string());
            }
            raw_bytes += bytes_read;
            chunks += 1;
            last_data_at = std::chrono::steady_clock::now();
            continue;
        }

        if (options.idle_timeout_s.has_value()) {
            const auto idle_s = std::chrono::duration<double>(now - last_data_at).count();
            if (idle_s >= *options.idle_timeout_s) {
                break;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    out.close();
    return truncate_to_ft_records(options.raw_out, raw_bytes, chunks);
}

double parse_double(const std::string& value, const char* name) {
    char* end = nullptr;
    const auto parsed = std::strtod(value.c_str(), &end);
    if (end == nullptr || *end != '\0') {
        throw CliError("invalid value for " + std::string(name) + ": " + value);
    }
    return parsed;
}

std::uint64_t parse_u64(const std::string& value, const char* name) {
    char* end = nullptr;
    const auto parsed = std::strtoull(value.c_str(), &end, 10);
    if (end == nullptr || *end != '\0') {
        throw CliError("invalid value for " + std::string(name) + ": " + value);
    }
    return parsed;
}

int parse_int(const std::string& value, const char* name) {
    char* end = nullptr;
    const auto parsed = std::strtol(value.c_str(), &end, 10);
    if (end == nullptr || *end != '\0') {
        throw CliError("invalid value for " + std::string(name) + ": " + value);
    }
    return static_cast<int>(parsed);
}

std::string next_arg(int& index, const int argc, char** argv, const char* name) {
    if (index + 1 >= argc) {
        throw CliError("missing value for " + std::string(name));
    }
    ++index;
    return argv[index];
}

}  // namespace

std::string FtKind::name() const {
    switch (raw) {
        case kFtKindBusChange:
            return "BUS_CHANGE";
        case kFtKindCe1Read:
            return "CE1_READ";
        case kFtKindCe1Write:
            return "CE1_WRITE";
        case kFtKindCe6Read:
            return "CE6_READ";
        case kFtKindCe6WriteAttempt:
            return "CE6_WRITE_ATTEMPT";
        case kFtKindSync:
            return "SYNC";
        case kFtKindOverflow:
            return "OVERFLOW";
        case kFtKindConfig:
            return "CONFIG";
        default: {
            std::ostringstream out;
            out << "UNKNOWN_" << std::uppercase << std::hex << std::setw(2) << std::setfill('0')
                << static_cast<int>(raw);
            return out.str();
        }
    }
}

bool FtKind::is_known() const {
    switch (raw) {
        case kFtKindBusChange:
        case kFtKindCe1Read:
        case kFtKindCe1Write:
        case kFtKindCe6Read:
        case kFtKindCe6WriteAttempt:
        case kFtKindSync:
        case kFtKindOverflow:
        case kFtKindConfig:
            return true;
        default:
            return false;
    }
}

std::string format_capture_start(
    const std::filesystem::path& raw_out,
    const std::optional<std::filesystem::path>& vcd_out,
    const std::optional<double>& duration_s,
    const std::optional<double>& idle_timeout_s,
    const std::optional<std::uint64_t>& max_bytes) {
    std::vector<std::string> parts;
    parts.push_back("raw=" + raw_out.string());
    if (vcd_out.has_value()) {
        parts.push_back("vcd=" + vcd_out->string());
    }
    if (duration_s.has_value()) {
        parts.push_back("duration=" + format_double_g(*duration_s) + "s");
    }
    if (idle_timeout_s.has_value()) {
        parts.push_back("idle_timeout=" + format_double_g(*idle_timeout_s) + "s");
    }
    if (max_bytes.has_value()) {
        parts.push_back("max_bytes=" + std::to_string(*max_bytes));
    }

    std::ostringstream out;
    out << "starting FT capture: ";
    for (std::size_t idx = 0; idx < parts.size(); ++idx) {
        if (idx != 0) {
            out << ", ";
        }
        out << parts[idx];
    }
    return out.str();
}

CaptureStats capture_to_vcd(const CaptureOptions& options) {
    const auto stats = capture_stream(options);
    if (options.vcd_out.has_value()) {
        write_vcd_from_capture(options.raw_out, *options.vcd_out);
    }
    return stats;
}

std::vector<FtRecord> read_ft_records(const std::filesystem::path& path) {
    const auto bytes = read_file_bytes(path);
    auto records = decode_ft_records(bytes);
    validate_ft_records(records);
    return records;
}

void write_vcd(const std::vector<FtRecord>& records, std::ostream& out) {
    write_vcd_records(records, out);
}

void write_vcd_from_capture(const std::filesystem::path& raw_path, const std::filesystem::path& vcd_path) {
    auto records = read_ft_records(raw_path);
    std::ofstream out(vcd_path, std::ios::trunc);
    if (!out) {
        throw std::runtime_error("failed to open " + vcd_path.string());
    }
    write_vcd(records, out);
}

void print_capture_help(std::ostream& out, const char* argv0) {
    out << "usage: " << argv0
        << " [-h] [--device-index DEVICE_INDEX] [--channel CHANNEL]\n"
        << "       [--read-timeout-ms READ_TIMEOUT_MS] --raw-out RAW_OUT\n"
        << "       [--vcd-out VCD_OUT] [--duration DURATION]\n"
        << "       [--idle-timeout IDLE_TIMEOUT] [--chunk-size CHUNK_SIZE]\n"
        << "       [--max-bytes MAX_BYTES]\n\n"
        << "Capture PC-E500 FT600 stream to .ft16 and optional .vcd\n\n"
        << "options:\n"
        << "  -h, --help            show this help message and exit\n"
        << "  --device-index DEVICE_INDEX\n"
        << "                        FT600 device index for D3XX open\n"
        << "  --channel CHANNEL     FT600 FIFO channel\n"
        << "  --read-timeout-ms READ_TIMEOUT_MS\n"
        << "                        D3XX read timeout in milliseconds\n"
        << "  --raw-out RAW_OUT     output .ft16 capture path\n"
        << "  --vcd-out VCD_OUT     optional output VCD path\n"
        << "  --duration DURATION   capture duration in seconds\n"
        << "  --idle-timeout IDLE_TIMEOUT\n"
        << "                        optional stop after this many idle seconds\n"
        << "  --chunk-size CHUNK_SIZE\n"
        << "                        host read chunk size in bytes\n"
        << "  --max-bytes MAX_BYTES\n"
        << "                        optional hard cap on captured bytes\n";
}

CaptureOptions parse_capture_args(const int argc, char** argv) {
    CaptureOptions options;

    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        if (arg == "-h" || arg == "--help") {
            print_capture_help(std::cout, argv[0]);
            std::exit(0);
        }
        if (arg == "--device-index") {
            options.device_index = parse_int(next_arg(index, argc, argv, "--device-index"), "--device-index");
        } else if (arg == "--channel") {
            options.channel = parse_int(next_arg(index, argc, argv, "--channel"), "--channel");
        } else if (arg == "--read-timeout-ms") {
            options.read_timeout_ms =
                static_cast<std::uint32_t>(parse_u64(next_arg(index, argc, argv, "--read-timeout-ms"),
                                                     "--read-timeout-ms"));
        } else if (arg == "--raw-out") {
            options.raw_out = next_arg(index, argc, argv, "--raw-out");
        } else if (arg == "--vcd-out") {
            options.vcd_out = std::filesystem::path(next_arg(index, argc, argv, "--vcd-out"));
        } else if (arg == "--duration") {
            options.duration_s = parse_double(next_arg(index, argc, argv, "--duration"), "--duration");
        } else if (arg == "--idle-timeout") {
            options.idle_timeout_s =
                parse_double(next_arg(index, argc, argv, "--idle-timeout"), "--idle-timeout");
        } else if (arg == "--chunk-size") {
            options.chunk_size =
                static_cast<std::size_t>(parse_u64(next_arg(index, argc, argv, "--chunk-size"), "--chunk-size"));
        } else if (arg == "--max-bytes") {
            options.max_bytes = parse_u64(next_arg(index, argc, argv, "--max-bytes"), "--max-bytes");
        } else {
            throw CliError("unrecognized argument: " + arg);
        }
    }

    if (options.raw_out.empty()) {
        throw CliError("the following arguments are required: --raw-out");
    }
    return options;
}

void print_ft_to_vcd_help(std::ostream& out, const char* argv0) {
    out << "usage: " << argv0 << " INPUT -o OUTPUT\n\n"
        << "Convert PC-E500 FT records to VCD\n\n"
        << "positional arguments:\n"
        << "  input                 raw FT capture file of 16-bit little-endian words\n\n"
        << "options:\n"
        << "  -h, --help            show this help message and exit\n"
        << "  -o, --output OUTPUT   output VCD path\n";
}

FtToVcdOptions parse_ft_to_vcd_args(const int argc, char** argv) {
    FtToVcdOptions options;
    bool have_input = false;

    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        if (arg == "-h" || arg == "--help") {
            print_ft_to_vcd_help(std::cout, argv[0]);
            std::exit(0);
        }
        if (arg == "-o" || arg == "--output") {
            options.output = next_arg(index, argc, argv, "--output");
        } else if (!arg.empty() && arg[0] != '-' && !have_input) {
            options.input = arg;
            have_input = true;
        } else {
            throw CliError("unrecognized argument: " + arg);
        }
    }

    if (!have_input) {
        throw CliError("the following arguments are required: input");
    }
    if (options.output.empty()) {
        throw CliError("the following arguments are required: -o/--output");
    }
    return options;
}

}  // namespace e500_ft
