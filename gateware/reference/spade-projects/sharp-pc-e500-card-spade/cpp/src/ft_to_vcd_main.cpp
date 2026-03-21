#include "e500_ft_host.hpp"

#include <exception>
#include <iostream>

int main(int argc, char** argv) {
    try {
        const auto options = e500_ft::parse_ft_to_vcd_args(argc, argv);
        e500_ft::write_vcd_from_capture(options.input, options.output);
        return 0;
    } catch (const e500_ft::CliError& exc) {
        std::cerr << exc.what() << std::endl;
        return 2;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << std::endl;
        return 1;
    }
}
