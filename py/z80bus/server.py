import io
import threading
import queue

from fastapi import FastAPI, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))

# Import components from your module.
from sed1560 import SED1560Parser, SED1560Interpreter
from bus_parser import PipelineBusParser

# ------------------------------------------------------------------------------
# Global Singleton: ParseRenderManager
# ------------------------------------------------------------------------------


class ParseRenderManager:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(ParseRenderManager, cls).__new__(cls)
        return cls._instance

    def reset(self):
        self.lcd_interpreter = SED1560Interpreter()
        self.out_ports_queue = queue.SimpleQueue()
        self.errors_queue = queue.SimpleQueue()
        self.parser = PipelineBusParser(self.errors_queue, self.out_ports_queue)

        self.buf = b""
        self.status_num_out_ports = 0
        self.status_num_lcd_commands = 0
        self.status_num_errors = 0

    def process_queues(self):
        while not self.errors_queue.empty():
            print(self.errors_queue.get_nowait())
            self.status_num_errors += 1

        events = []
        while not self.out_ports_queue.empty():
            events.append(self.out_ports_queue.get_nowait())
            self.status_num_out_ports += 1
        commands = SED1560Parser.parse_bus_commands(events)
        for c in commands:
            self.status_num_lcd_commands += 1
            self.lcd_interpreter.eval(c)


    def process_raw_data(self, data: bytes) -> list:
        self.buf += data
        self.buf = self.parser.parse(self.buf)
        self.process_queues()

    def stats(self):
        out_ports_queue_size_before = self.out_ports_queue.qsize()

        self.buf = self.parser.parse(self.buf)
        # self.parser.flush()
        self.process_queues()

        out_ports_queue_size_after = self.out_ports_queue.qsize()

        return self.parser.stats() | {
            "2num_out_ports": self.status_num_out_ports,
            "2num_lcd_commands": self.status_num_lcd_commands,
            "2num_errors": self.status_num_errors,
            "2out_ports_queue_size": self.out_ports_queue.qsize(),
            "2errors_queue_size": self.errors_queue.qsize(),
            "2out_ports_queue_size_before": out_ports_queue_size_before,
            "2out_ports_queue_size_after": out_ports_queue_size_after,
        }

    def get_accumulated_events(self) -> list:
        return self.parser.all_events

    def get_lcd_image_bytes(self) -> bytes:
        img = self.lcd_interpreter.vram_image()
        img_bytes_io = io.BytesIO()
        img.save(img_bytes_io, format="PNG")
        img_bytes_io.seek(0)
        return img_bytes_io.getvalue()


manager = ParseRenderManager()

# ------------------------------------------------------------------------------
# FastAPI Application
# ------------------------------------------------------------------------------

app = FastAPI(
    title="retrobus-explorer",
    description="API for continuous bus-data parsing and LCD rendering.",
    version="1.0.0",
)


@app.get("/events", summary="Retrieve accumulated events")
async def get_events():
    events = manager.get_accumulated_events()
    return JSONResponse(content={"events": events})


@app.get("/lcd")
async def get_lcd():
    img_bytes = manager.get_lcd_image_bytes()
    return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    manager.reset()
    status_num_packets_get = 0
    status_num_bytes_get = 0
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            status_num_packets_get += 1
            status_num_bytes_get += len(data)
            manager.process_raw_data(data)

    except WebSocketDisconnect:
        print("WebSocket client disconnected.")

    print(manager.stats())
    print(
        {
            "status_num_packets_get": status_num_packets_get,
            "status_num_bytes_get": status_num_bytes_get,
        }
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
