#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cstdint>
#include <vector>

static std::uint16_t load_u16(const unsigned char* src, int swap_bytes_within_u16) {
    if (swap_bytes_within_u16) {
        return static_cast<std::uint16_t>(src[1]) |
               (static_cast<std::uint16_t>(src[0]) << 8);
    }
    return static_cast<std::uint16_t>(src[0]) |
           (static_cast<std::uint16_t>(src[1]) << 8);
}

static PyObject* decode_words(PyObject* /* self */, PyObject* args, PyObject* kwargs) {
    Py_buffer data = {};
    Py_buffer pending = {};
    int swap_bytes_within_u16 = 0;
    static const char* kwlist[] = {"data", "pending", "swap_bytes_within_u16", nullptr};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "y*|y*p:decode_words",
            const_cast<char**>(kwlist),
            &data,
            &pending,
            &swap_bytes_within_u16)) {
        return nullptr;
    }

    std::vector<unsigned char> merged;
    merged.reserve(static_cast<std::size_t>(pending.len + data.len));
    const auto* pending_bytes = static_cast<const unsigned char*>(pending.buf);
    const auto* data_bytes = static_cast<const unsigned char*>(data.buf);
    merged.insert(merged.end(), pending_bytes, pending_bytes + pending.len);
    merged.insert(merged.end(), data_bytes, data_bytes + data.len);

    const Py_ssize_t word_count = static_cast<Py_ssize_t>(merged.size() / 4);
    PyObject* words = PyList_New(word_count);
    if (words == nullptr) {
        PyBuffer_Release(&data);
        if (pending.buf != nullptr) {
            PyBuffer_Release(&pending);
        }
        return nullptr;
    }

    for (Py_ssize_t index = 0; index < word_count; ++index) {
        const auto offset = static_cast<std::size_t>(index) * 4;
        const std::uint16_t lo = load_u16(&merged[offset], swap_bytes_within_u16);
        const std::uint16_t hi = load_u16(&merged[offset + 2], swap_bytes_within_u16);
        const std::uint32_t word =
            static_cast<std::uint32_t>(lo) | (static_cast<std::uint32_t>(hi) << 16);
        PyObject* value = PyLong_FromUnsignedLong(word);
        if (value == nullptr) {
            Py_DECREF(words);
            PyBuffer_Release(&data);
            if (pending.buf != nullptr) {
                PyBuffer_Release(&pending);
            }
            return nullptr;
        }
        PyList_SET_ITEM(words, index, value);
    }

    const auto remainder_offset = static_cast<std::size_t>(word_count) * 4;
    PyObject* remainder = PyBytes_FromStringAndSize(
        reinterpret_cast<const char*>(merged.data() + remainder_offset),
        static_cast<Py_ssize_t>(merged.size() - remainder_offset));
    if (remainder == nullptr) {
        Py_DECREF(words);
        PyBuffer_Release(&data);
        if (pending.buf != nullptr) {
            PyBuffer_Release(&pending);
        }
        return nullptr;
    }

    PyObject* result = PyTuple_New(2);
    if (result == nullptr) {
        Py_DECREF(words);
        Py_DECREF(remainder);
        PyBuffer_Release(&data);
        if (pending.buf != nullptr) {
            PyBuffer_Release(&pending);
        }
        return nullptr;
    }
    PyTuple_SET_ITEM(result, 0, words);
    PyTuple_SET_ITEM(result, 1, remainder);

    PyBuffer_Release(&data);
    if (pending.buf != nullptr) {
        PyBuffer_Release(&pending);
    }
    return result;
}

static PyMethodDef module_methods[] = {
    {
        "decode_words",
        reinterpret_cast<PyCFunction>(decode_words),
        METH_VARARGS | METH_KEYWORDS,
        "Decode FT600 byte stream into 32-bit sampled-bus words.",
    },
    {nullptr, nullptr, 0, nullptr},
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "pc_e500_ft600_native",
    "Native decoder for PC-E500 FT600 sampled-bus words",
    -1,
    module_methods,
};

PyMODINIT_FUNC PyInit_pc_e500_ft600_native(void) {
    return PyModule_Create(&module_def);
}
