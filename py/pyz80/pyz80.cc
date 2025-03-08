#include <pybind11/functional.h>
#include <pybind11/pybind11.h>

#include "z80.hpp"

namespace py = pybind11;

class PyZ80 {
 public:
  Z80 z80;

  PyZ80(py::function readByte, py::function writeByte, py::function inPort,
        py::function outPort, bool returnPortAs16Bits = false)
      : z80(
            [readByte](void* /*arg*/, unsigned short addr) -> unsigned char {
              py::gil_scoped_acquire acquire;
              return readByte(addr).cast<unsigned char>();
            },
            [writeByte](void* /*arg*/, unsigned short addr,
                        unsigned char value) {
              py::gil_scoped_acquire acquire;
              writeByte(addr, value);
            },
            [inPort](void* /*arg*/, unsigned short port) -> unsigned char {
              py::gil_scoped_acquire acquire;
              return inPort(port).cast<unsigned char>();
            },
            [outPort](void* /*arg*/, unsigned short port, unsigned char value) {
              py::gil_scoped_acquire acquire;
              outPort(port, value);
            },
            nullptr, returnPortAs16Bits) {}

  // Execute a given number of clock cycles
  int execute(int clocks) { return z80.execute(clocks); }

  // Request to break the execution
  void request_break() { z80.requestBreak(); }

  // Generate an IRQ with a given vector
  void generate_irq(int vector) { z80.generateIRQ(vector); }

  // Generate an NMI with a given address
  void generate_nmi(int address) { z80.generateNMI(address); }

  // Set a debug message callback (for dynamic disassembly, etc.)
  void set_debug_message(py::function debug_callback) {
    z80.setDebugMessage([debug_callback](void* /*arg*/, const char* msg) {
      py::gil_scoped_acquire acquire;
      debug_callback(std::string(msg));
    });
  }

  // Set a callback to be notified when clocks are consumed
  void set_consume_clock_callback(py::function clock_callback) {
    z80.setConsumeClockCallback([clock_callback](void* /*arg*/, int clocks) {
      py::gil_scoped_acquire acquire;
      clock_callback(clocks);
    });
  }
};

PYBIND11_MODULE(pyz80, m) {
  m.doc() = "Python wrapper for the SUZUKI PLAN Z80 Emulator using pybind11";

  py::class_<PyZ80>(m, "Z80")
      .def(py::init<py::function, py::function, py::function, py::function,
                    bool>(),
           py::arg("readByte"), py::arg("writeByte"), py::arg("inPort"),
           py::arg("outPort"), py::arg("returnPortAs16Bits") = false)
      .def("execute", &PyZ80::execute, "Execute a given number of clock cycles")
      .def("request_break", &PyZ80::request_break, "Request break in execution")
      .def("generate_irq", &PyZ80::generate_irq,
           "Generate an IRQ with a given vector")
      .def("generate_nmi", &PyZ80::generate_nmi,
           "Generate an NMI with a given address")
      .def("set_debug_message", &PyZ80::set_debug_message,
           "Set a debug message callback")
      .def("set_consume_clock_callback", &PyZ80::set_consume_clock_callback,
           "Set the clock consumption callback");
}

