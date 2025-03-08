#include <pybind11/functional.h>
#include <pybind11/pybind11.h>

#include "z80.hpp"

namespace py = pybind11;

class PyRegisterPair {
 private:
  Z80::RegisterPair p;

 public:
  PyRegisterPair(const Z80::RegisterPair& val) : p(val) {}

  unsigned char A() const { return p.A; }
  unsigned char F() const { return p.F; }
  unsigned char B() const { return p.B; }
  unsigned char C() const { return p.C; }
  unsigned char D() const { return p.D; }
  unsigned char E() const { return p.E; }
  unsigned char H() const { return p.H; }
  unsigned char L() const { return p.L; }
};

class PyRegister {
  private:
    Z80::Register r;
  public:
    PyRegister(const Z80::Register& val) : r(val) {}

    PyRegisterPair pair() const { return PyRegisterPair(r.pair); }
    PyRegisterPair back() const { return PyRegisterPair(r.back); }
    unsigned short PC() const { return r.PC; }
    unsigned short SP() const { return r.SP; }
    unsigned short IX() const { return r.IX; }
    unsigned short IY() const { return r.IY; }
    unsigned short interruptVector() const { return r.interruptVector; }
    unsigned short interruptAddrN() const { return r.interruptAddrN; }
    unsigned short WZ() const { return r.WZ; }
    unsigned char R() const { return r.R; }
    unsigned char I() const { return r.I; }
    unsigned char IFF() const { return r.IFF; }
};

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

  PyRegister reg() const { return PyRegister(z80.reg); }

  unsigned short PC() const { return z80.reg.PC; }
  void setPC(unsigned short value) { z80.reg.PC = value; }
};

PYBIND11_MODULE(pyz80, m) {
  m.doc() = "Python wrapper for the SUZUKI PLAN Z80 Emulator using pybind11";

  py::class_<PyRegisterPair>(m, "RegisterPair")
      .def_property_readonly("A", &PyRegisterPair::A)
      .def_property_readonly("F", &PyRegisterPair::F)
      .def_property_readonly("B", &PyRegisterPair::B)
      .def_property_readonly("C", &PyRegisterPair::C)
      .def_property_readonly("D", &PyRegisterPair::D)
      .def_property_readonly("E", &PyRegisterPair::E)
      .def_property_readonly("H", &PyRegisterPair::H)
      .def_property_readonly("L", &PyRegisterPair::L);

  py::class_<PyRegister>(m, "Register")
      .def_property_readonly("pair", &PyRegister::pair)
      .def_property_readonly("back", &PyRegister::back)
      .def_property_readonly("PC", &PyRegister::PC)
      .def_property_readonly("SP", &PyRegister::SP)
      .def_property_readonly("IX", &PyRegister::IX)
      .def_property_readonly("IY", &PyRegister::IY)
      .def_property_readonly("interruptVector", &PyRegister::interruptVector)
      .def_property_readonly("interruptAddrN", &PyRegister::interruptAddrN)
      .def_property_readonly("WZ", &PyRegister::WZ)
      .def_property_readonly("R", &PyRegister::R)
      .def_property_readonly("I", &PyRegister::I)
      .def_property_readonly("IFF", &PyRegister::IFF);

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
           "Set the clock consumption callback")
      .def_property_readonly("reg", &PyZ80::reg, "Get the current register state")
      .def_property("PC", &PyZ80::PC, &PyZ80::setPC, "Get or set the PC");
}

