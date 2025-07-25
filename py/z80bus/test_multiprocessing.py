import multiprocessing as mp
import queue

import PIL

from z80bus import bus_parser, sed1560
from z80bus.bus_parser import Event, IOPort, Type
from z80bus.test_bus_parser import fetch, out_port


def test_parse_context():
    return
    raw_queue = mp.Queue()
    all_events_queue = mp.Queue()
    errors_queue = mp.Queue()
    ports_queue = mp.Queue()

    with bus_parser.ParseContext(
        raw_queue, all_events_queue, errors_queue, ports_queue
    ):
        raw_queue.put(out_port(0xAB, bus_parser.IOPort.LCD_COMMAND))
        try:
            ports_queue.get_nowait()
            raise AssertionError
        except queue.Empty:
            pass
        raw_queue.put(fetch(0x00, 0x1234))
        assert ports_queue.get() == Event(
            type=Type.OUT_PORT,
            port=IOPort.LCD_COMMAND,
            val=0xAB,
            addr=IOPort.LCD_COMMAND.value,
        )
    assert ports_queue.get() is None


def test_draw_lcd_context():
    return
    raw_queue = mp.Queue()
    all_events_queue = mp.Queue()
    errors_queue = mp.Queue()
    ports_queue = mp.Queue()
    display_queue = mp.Queue()

    def assert_display_queue_empty():
        try:
            display_queue.get_nowait()
            raise AssertionError
        except queue.Empty:
            pass

    with sed1560.DrawLCDContext(ports_queue, display_queue):
        with bus_parser.ParseContext(
            raw_queue, all_events_queue, errors_queue, ports_queue
        ):
            assert_display_queue_empty()

            raw_queue.put(out_port(0x02, bus_parser.IOPort.LCD_COMMAND))
            raw_queue.put(fetch(0x00, 0x1234))
            assert isinstance(display_queue.get(), PIL.Image.Image)

            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            assert isinstance(display_queue.get(), PIL.Image.Image)

            # should not put image if it's same as old one
            raw_queue.put(out_port(0x02, bus_parser.IOPort.LCD_COMMAND))
            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            assert_display_queue_empty()

            # it should only put image to the queue if it's empty
            raw_queue.put(out_port(0x02, bus_parser.IOPort.LCD_COMMAND))
            raw_queue.put(fetch(0x00, 0x1234))
            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            raw_queue.put(out_port(0x01, bus_parser.IOPort.LCD_OUT))
            raw_queue.put(fetch(0x00, 0x1234))
            assert isinstance(display_queue.get(), PIL.Image.Image)
            assert_display_queue_empty()
    # assert False
