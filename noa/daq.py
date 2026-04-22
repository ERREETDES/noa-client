import asyncio
from enum import Enum, auto
import json

from attrs import define
from cattrs import Converter

from .typecast import Typecast

converter = Converter()

class TriggerKind(Enum):
    Immediate = "Immediate"
    RisingEdge = "RisingEdge"
    FallingEdge = "FallingEdge"
    BothEdges = "BothEdges"
    TriggerIn = "TriggerIn"
    EqualTo = "EqualTo"
    GreaterThan = "GreaterThan"
    LessThan = "LessThan"
    Between = "Between"

@define
class DaqTrigger:
    kind: TriggerKind
    channel: int | None =None
    a: int | None=None
    b: int | None=None
    threshold: int | None=None
    hysteresis: int | None=None

    def serialize(self) -> bytes:
        return json.dumps(converter.unstructure(self)).encode("utf-8")

class DAQ:
    def __init__(self, noa, prefix, log) -> None:
        self._noa = noa
        self._prefix = noa._ov_prefix + "." + prefix
        self._log = log.getChild(prefix)
        self._window_size = 0
        self._data_q = {}
        self._subs = {}
        self._needs_reset = True

    async def reset(self):
        self._log.debug("reset")
        self._window_size = 0
        self._data_q.clear()
        self._subs.clear()

        await self._noa._req_expect_ok(self._prefix+".reset")
    
    async def setup_data(self, window_size=1000, decimation=1, delay=0):
        """ DAQ data setup """
        self._log.debug(f"setup_data: window_size={window_size}, decimation={decimation}, delay={delay}")
        if self._needs_reset:
            await self.reset()

        self._needs_reset = False

        assert self._noa.is_running(), "Load a bitstream first"

        await self._noa._req_expect_ok(
            self._prefix+".setup-data",
            json.dumps({
                "window_size": window_size,
                "decimation": decimation,
                "delay": delay
            }).encode()
        )

        self._window_size = window_size
    
    async def enable_channel(self, channel: int, dtype: str="uint32", cb=None, max_queue_size=100):
        """ Enable a DAQ channel. If specified, cb is awaited once per DAQ window"""
        self._log.debug(f"enable_channel: channel={channel}, dtype={dtype}")

        assert isinstance(channel, int) and channel >= 0 and channel < 64, "Invalid channel index"

        converter = Typecast(dtype).from_bytes

        if cb is None:
            # By default, store data in a queue accessible by self.read
            q = asyncio.Queue(maxsize=max_queue_size)
            self._data_q[channel] = q

            async def callback(msg):
                data = converter(msg.data)
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    self._log.warning(f"ch{channel} queue full.")
        else:
            # Or use user-specified callback
            async def callback(msg):
                data = converter(msg.data)
                await cb(channel, data)

        self._subs[channel] = await self._noa._nc.subscribe(f"{self._prefix}.ch{channel}.*", cb=callback)
    
    async def disable_channel(self, channel):
        """ Disable previously-enabled DAQ channel """
        self._log.debug(f"disable_channel {channel}")
        if channel not in self._subs:
            return

        await self._subs[channel].unsubscribe()
    
    async def trigger(self, opts: DaqTrigger):
        """ Start acquisition with specified trigger options. """
        self._log.debug(f"trigger: {opts}")
        assert self._noa.is_running(), "Load a bitstream first"
        assert self._window_size > 0, "Call setup_data first"

        await self._noa._req_expect_ok(
            self._prefix+".setup-trigger",
            opts.serialize()
        )
    
    async def read(self, channel):
        """ Read a single data window for a channel enabled with the default cb. """
        q = self._data_q[channel]
        
        if q is None:
            raise RuntimeError("Called read on an invalid channel. Make sure you called enable_chanel with cb=None")
        
        return await q.get()
    
    def read_ready(self, channel):
        """ Returns True when the channel can be read without blocking """
        q = self._data_q[channel]
        
        if q is None:
            raise RuntimeError("Called read_ready on an invalid channel. Make sure you called enable_chanel with cb=None")
        
        return not q.empty()