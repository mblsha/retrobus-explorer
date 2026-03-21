#include "e500_ft_host.hpp"

#include <exception>
#include <iostream>

int main(int argc, char** argv) {
    try {
        const auto options = e500_ft::parse_capture_args(argc, argv);
        std::cout << e500_ft::format_capture_start(
                         options.raw_out, options.vcd_out, options.duration_s, options.idle_timeout_s,
                         options.max_bytes)
                  << std::endl;
        const auto stats = e500_ft::capture_to_vcd(options);
        std::cout << "captured " << stats.aligned_bytes << " bytes in " << stats.chunks << " chunk(s)";
        if (stats.trimmed_bytes != 0) {
            std::cout << ", trimmed " << stats.trimmed_bytes << " trailing byte(s)";
        }
        std::cout << std::endl;
        if (options.vcd_out.has_value()) {
            std::cout << "wrote " << options.vcd_out->string() << std::endl;
        }
        std::cout << "wrote " << options.raw_out.string() << std::endl;
        return 0;
    } catch (const e500_ft::CliError& exc) {
        std::cerr << exc.what() << std::endl;
        return 2;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << std::endl;
        return 1;
    }
}
