import ast
import asyncio
from enum import Enum
import json
import logging
import os
import socket
from typing import Dict

import attrs
import nats
from nats.aio.client import Client

from attrs import define
import cattrs

from pathlib import Path

from .analog_out import Aout
from .daq import DAQ, DaqTrigger, TriggerKind
from .digital_io import DIOPort
from . import digital_io
from .stream_in import StreamIn
from .typecast import Typecast

converter = cattrs.Converter()



class ManagerState(Enum):
    IDLE = "IDLE"
    CONNECTED = "CONNECTED"
    RUNNING = "RUNNING"


@define
class DeviceInfo:
    model: str
    serial_number: str = ""
    software_version: str = ""
    uptime: str = ""
    disk_usage: str = ""
    current_time: str = ""

    def serialize(self) -> bytes:
        return json.dumps(converter.unstructure(self)).encode("utf-8")

    @classmethod
    def deserialize(cls, s: bytes) -> "DeviceInfo":
        return converter.structure(json.loads(s), cls)


@define
class ManagerStatus:
    params: Dict[str, str]
    state: ManagerState = ManagerState.IDLE
    host: str = ""
    overlay: str = ""
    overlay_prefix: str = ""

    def serialize(self) -> bytes:
        return json.dumps(converter.unstructure(self)).encode("utf-8")

    @classmethod
    def deserialize(cls, s: bytes) -> "ManagerStatus":
        return converter.structure(json.loads(s), cls)


@define
class Channel:
    subject: str
    gain: float
    offset: float
    timestep: float
    signed: bool
    bits: int


@define
class OverlayStatus:
    run_id: str
    bitstream_name: str
    program_time: str
    channels: Dict[str, Channel]
    params: Dict[str, str]

    def serialize(self) -> bytes:
        return json.dumps(converter.unstructure(self)).encode("utf-8")

    @classmethod
    def deserialize(cls, s: bytes) -> "OverlayStatus":
        return converter.structure(json.loads(s), cls)


@define
class AnalogOutputs: ...


class Noa:
    def __init__(self, addr: str, log: logging.Logger | None = None):
        self._nc: Client = None  # type: ignore
        self._addr = addr

        if log is None:
            logging.basicConfig(level=logging.INFO)
            self._log = logging.getLogger()
        else:
            self._log: logging.Logger = log

        self._mgr_prefix = ""
        self._ov_prefix = ""
        self._mgr_status_sub = None
        self._ov_status_sub = None
        self._mgr_status: ManagerStatus = None  # type: ignore
        self._ov_status: OverlayStatus = None  # type: ignore
        self._host_id = ""
        self._window_size = -1

        self._read_regs = {}
        self._write_converters = {}
        self._write_offsets = {}
        self._running = False

    async def __aenter__(self):
        """Use `async with` notation to automatically disconnect from the target after exiting from the block"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def is_connected(self) -> bool:
        """Returns True when connected to the target"""
        return self._nc is not None

    def is_running(self):
        """Returns True when the target is running"""
        return self.is_connected() and self._mgr_status.state == ManagerState.RUNNING

    async def connect(self, host_id=None):
        """Connect to the target. Not necessary when using `async with` notation. Remember to call .disconnect when done."""
        self._log.info(f"Connecting to '{self._addr}'")
        try:
            self._read_regs.clear()

            if self._mgr_status_sub is not None:
                await self._mgr_status_sub.unsubscribe()

            if self._ov_status_sub is not None:
                await self._ov_status_sub.unsubscribe()  # type: ignore

            self._ov_prefix = ""

            if host_id is None:
                host_id = f"{os.getlogin()}@{socket.gethostname()} (NOA Python Client)"

            self._nc = await nats.connect(self._addr)
            self._log.info(f"Connected to {self._addr}")

            response = (
                await self._nc.request("noa.MANAGER.ping", timeout=2)
            ).data.decode()
            self._mgr_prefix = f"noa.{response}"

            self._log.debug(f"Manager is {self._mgr_prefix}")

            self._mgr_status_sub = await self._nc.subscribe(
                self._mgr_prefix + ".status", cb=self._on_mgr_status
            )
            await self._nc.request("noa.MANAGER.ping")

            while self._mgr_status is None:
                await asyncio.sleep(0.05)

            if (
                self._mgr_status.state != ManagerState.IDLE
                and self._mgr_status.host != host_id
            ):
                self._log.error(
                    f"Device is already taken by host {self._mgr_status.host}"
                )
                raise RuntimeError(
                    f"Device already taken by host '{self._mgr_status.host}'"
                )

            if self.is_running():
                await self._connect_to_ov()
        except Exception:
            self._nc = None  # type: ignore
            self._log.error("Failed to connect.")
            raise

        await self._req_expect_ok(self._mgr_prefix + ".connect", host_id.encode())

    async def disconnect(self):
        """Disconnect from the target."""
        if self.is_connected():
            await self._req_expect_ok(self._mgr_prefix + ".disconnect")
            await self._nc.drain()  # type: ignore

        self._mgr_status = None  # type: ignore
        self._nc = None  # type: ignore
        self._log.info("Disconnected!")

    async def load_bitstream(self, bit: os.PathLike, hwh: os.PathLike):
        """Load a bitstream and hardware handoff pair to the target."""

        assert self.is_connected()

        bit = Path(bit)
        hwh = Path(hwh)

        assert bit.is_file()
        assert hwh.is_file()

        # Upload bitstream
        self._log.info("Uploading:")
        self._log.info(f"    Hardware handoff: {hwh.as_posix()}")
        await self._req_expect_ok(self._mgr_prefix + ".send-hwh", hwh.read_bytes())

        self._log.info(f"    Bitstream: {bit.as_posix()}")
        await self._req_expect_ok(
            self._mgr_prefix + ".send-bitstream", bit.read_bytes(), timeout=60
        )
        await self._req_expect_ok(self._mgr_prefix + ".load-bitstream", timeout=20)
        assert self.is_running()

        await self._connect_to_ov()

        self._log.info(f"Programming complete.")

    async def device_info(self) -> DeviceInfo:
        """Requests a DeviceInfo struct from the target"""
        assert self.is_connected()

        response = await self._nc.request(self._mgr_prefix + ".get-device-info")
        return DeviceInfo.deserialize(response.data)

    async def setup_read_register(
        self, name: str, offset: int, cb=None, dtype="uint32"
    ):
        """Configure a read register"""

        self._log.debug(f"Creating read register {name} at {hex(offset)} ({dtype}, cb={cb})")

        assert self.is_connected()

        converter = Typecast(dtype).from_bytes

        async def callback(msg):
            await self._on_reg_update(name, msg, converter, cb)

        await self._nc.subscribe(
            f"{self._mgr_status.overlay_prefix}.reg.{offset:x}", cb=callback
        )

        await self._req_expect_ok(
            self._ov_prefix + ".create-read-reg", f"{offset:x}".encode()
        )

        for _ in range(20):
            if name in self._read_regs:
                return

            await asyncio.sleep(0.1)

        raise RuntimeError("Did not receive initial register value")

    async def setup_write_register(self, name: str, offset: int, dtype="uint32"):
        """Configure a write register to the target"""
        self._log.debug(f"Creating write register {name} at {hex(offset)} ({dtype})")
        t = Typecast(dtype)
        self._write_converters[name] = lambda f: t.to_bytes(t.from_float(f))

        self._write_offsets[name] = offset
        await self._req_expect_ok(
            self._ov_prefix + ".create-write-reg", f"{offset:x}".encode()
        )

    def read_register(self, name) -> int | float:
        """Read the value of a read register previously configured with setup_read_register"""
        return self._read_regs[name]

    async def write_register(self, name, value: int | float):
        """Write to a write register previously configured with setup_write_register"""
        data = self._write_converters[name](value)
        offset = self._write_offsets[name]

        self._log.debug(f"{name} <= {value} ({data})")
        await self._nc.publish(self._ov_prefix + f".write-reg.{offset:x}", data)

    async def enable_analog_outputs(
        self, A0_to_A3: bool = True, A4_to_A7: bool = True, A8_to_A11: bool = True
    ):
        """Enable/disable analog outputs. Used with the analog output port's .setup method to configure an analog output"""
        await self._req_expect_ok(
            self._ov_prefix + ".aout-enable",
            json.dumps(
                {
                    "A0_to_A3": A0_to_A3,
                    "A4_to_A7": A4_to_A7,
                    "A8_to_A11": A8_to_A11,
                }
            ).encode(),
        )

    async def _on_reg_update(self, name: str, msg, converter, cb):
        val = converter(msg.data)[0]
        self._read_regs[name] = val

        self._log.debug(f"{name} => {val} ({msg.data})")

        if cb:
            await cb(name, val)

    async def _setparam(self, param: str, value: bytes):
        await self._nc.publish(self._ov_prefix + ".setparam." + param, value)

    async def _connect_to_ov(self):

        self._ov_prefix = self._mgr_status.overlay_prefix
        await self._nc.subscribe(self._ov_prefix + ".status", cb=self._on_ov_status)
        await self._nc.request(self._ov_prefix + ".ping")

        for _ in range(50):
            if self._ov_status:
                break

            await asyncio.sleep(0.1)

        assert self._ov_status

        # todo: populate peripherals based on actual bistream contents
        # instead of hardcoding reference design
        self.DA = DIOPort(self, "DA", digital_io.ARCH1_DA, self._log)
        self.DB = DIOPort(self, "DB", digital_io.ARCH1_DB, self._log)

        for i in range(12):
            setattr(self, f"A{i}", Aout(self, i, self._log))

        self.stream_in = StreamIn(self, "matlab_stream_in", self._log)
        self.daq = DAQ(self, "daq_0", self._log)

    async def _req_expect_ok(self, subject, payload=b"", timeout=2):
        assert self._nc is not None
        response = await self._nc.request(subject, payload, timeout=timeout)

        if response.data != b"OK":
            raise RuntimeError(f"Request {subject} returned {response.data.decode()}")

    async def _on_mgr_status(self, reply):
        self._log.debug(f"Manager status: {reply.data}")
        self._mgr_status = ManagerStatus.deserialize(reply.data)

    async def _on_ov_status(self, reply):
        self._log.debug(f"Overlay status: {reply.data}")
        self._ov_status = OverlayStatus.deserialize(reply.data)


async def _main():
    # When executed direcly, expose a CLI that allows the execution of examples
    # or a combination of direct manual operations.

    import argparse
    import sys

    from examples.analog_out import example as analog_out
    from examples.daq import example as daq
    from examples.digital_io import example as digital_io
    from examples.registers import example as registers
    from examples.stream_in import example as stream_in

    import numpy as np

    EXAMPLES = {
        "analog_out": analog_out,
        "daq": daq,
        "digital_io": digital_io,
        "registers": registers,
        "stream_in": stream_in,
    }

    parser = argparse.ArgumentParser(
        prog="noa.py",
        description="Interract with NOA hardware programatically.",
        epilog="see https://docs.rexys.io for more information.",
    )

    parser.add_argument(
        "addr", help="Device address (i.e. arch1-00001.local or 192.168.1.12)"
    )
    parser.add_argument("-v", action="store_true", help="verbose mode")

    group = parser.add_argument_group("Run an example")
    group.add_argument(
        "--example",
        metavar="name",
        choices=EXAMPLES.keys(),
        help=f"Run a built-in example ({', '.join(EXAMPLES.keys())})",
    )

    group = parser.add_argument_group("Manual operation")
    group.add_argument("--bit", metavar="path", type=Path, help="load a bitstream file")
    group.add_argument(
        "--hwh", metavar="path", type=Path, help="specify a different hwh file"
    )
    group.add_argument(
        "--device-info", action="store_true", help="Print device information"
    )
    group.add_argument(
        "--digital-inputs",
        nargs="+",
        metavar="signal:bit:port:pin",
        help="Configure digital inputs (1:0:DA:16 1:1:DB:32)",
    )
    group.add_argument(
        "--digital-outputs",
        nargs="+",
        metavar="signal:bit:port:pin",
        help="Configure digital outputs",
    )
    group.add_argument(
        "--analog-outputs",
        nargs="+",
        metavar="signal:port:sigmin:sigmax:vmin:vmax",
        help="Configure analog outputs (0:A2:-1:1:-5:5 1:A3:0:1:0:5)",
    )
    group.add_argument(
        "--read",
        metavar="offset",
        nargs="+",
        help='read registers to stdout (i.e. --read 0x100 0x104 "0x10C:fixdt(1,16,5)"',
    )
    group.add_argument(
        "--write",
        metavar="expr",
        nargs="+",
        help="write registers (i.e. --write 0x100=0 0x104=1:int8",
    )
    group.add_argument(
        "--stream-in", metavar="path", help="stream data from a file (or '-' for stdin)"
    )
    group.add_argument(
        "--stream-in-dtype",
        metavar="dtype",
        default="uint32",
        help="data type for streaming (default: uint32)",
    )
    group.add_argument(
        "--daq-output",
        metavar="path",
        help="Save DAQ data to a CSV file (or '-' for stdout)",
    )
    group.add_argument(
        "--daq-channels",
        nargs="+",
        metavar="ch[:dtype]",
        help="DAQ channels to record (e.g. 0:fixdt(1,16,5) 1)",
    )
    group.add_argument(
        "--daq-window", type=int, default=1000, help="DAQ window size (default: 1000)"
    )
    group.add_argument(
        "--daq-decimation", type=int, default=1, help="DAQ decimation (default: 1)"
    )
    group.add_argument(
        "--daq-delay", type=int, default=0, help="DAQ delay (default: 0)"
    )
    group.add_argument(
        "--daq-nb-windows",
        type=int,
        default=1,
        help="Number of windows to record (default: 1)",
    )
    group.add_argument(
        "--daq-trigger",
        choices=[k.name for k in TriggerKind],
        default="Immediate",
        help="Trigger kind (default: Immediate)",
    )
    group.add_argument("--daq-trigger-ch", type=int, help="Trigger channel index")
    group.add_argument("--daq-trigger-a", type=int, help="Trigger 'a' parameter")
    group.add_argument("--daq-trigger-b", type=int, help="Trigger 'b' parameter")
    group.add_argument("--daq-trigger-threshold", type=int, help="Trigger threshold")
    group.add_argument("--daq-trigger-hysteresis", type=int, help="Trigger hysteresis")
    group.add_argument(
        "--disconnect", action="store_true", help="disconnects from the target"
    )

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        return

    if args.v:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)-8s %(name)-18s: %(message)s",
            stream=sys.stderr,
        )
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    log = logging.getLogger("noa")

    if args.example:
        example_module = EXAMPLES[args.example]

        # Use example's default bit/hwh files relative to the current directory
        base_path = Path("examples") / args.example
        bit = base_path / "design_1_wrapper.bit"
        hwh = base_path / "design_1.hwh"

        await example_module.run(args.addr, bit, hwh, logger=log)
        return

    noa = Noa(args.addr, log=log)

    try:
        await noa.connect()

        if args.device_info:
            log.info("Device Information:")
            dev_info = await noa.device_info()
            for field, value in attrs.asdict(dev_info).items():
                label = field.replace("_", " ").title()
                log.info(f"  {label:17}: {value}")

        if args.bit:
            if args.hwh:
                hwh = args.hwh
            else:
                hwh = args.bit.with_suffix(".hwh")

            await noa.load_bitstream(args.bit, hwh)

        if args.digital_inputs or args.digital_outputs:
            port_configs = {
                "DA": {"inputs": [], "outputs": []},
                "DB": {"inputs": [], "outputs": []},
            }

            if args.digital_inputs:
                for arg in args.digital_inputs:
                    sig, bit, port, pin = arg.split(":")
                    port_configs[port]["inputs"].append(
                        digital_io.PinMap(
                            sig=int(sig, 0), bit=int(bit, 0), pin=int(pin, 0)
                        )
                    )

            if args.digital_outputs:
                for arg in args.digital_outputs:
                    sig, bit, port, pin = arg.split(":")
                    port_configs[port]["outputs"].append(
                        digital_io.PinMap(
                            sig=int(sig, 0), bit=int(bit, 0), pin=int(pin, 0)
                        )
                    )

            for port_name, config in port_configs.items():
                if config["inputs"] or config["outputs"]:
                    await getattr(noa, port_name).setup(
                        inputs=config["inputs"], outputs=config["outputs"]
                    )

            await asyncio.sleep(0.1)

        if args.analog_outputs:
            # Enable analog outputs if one or more are specified
            await noa.enable_analog_outputs()
            for arg in args.analog_outputs:
                sig, port_name, sigmin, sigmax, vmin, vmax = arg.split(":")
                await getattr(noa, port_name).setup(
                    signal=int(sig, 0),
                    signal_range=[float(sigmin), float(sigmax)],
                    voltage_range=[float(vmin), float(vmax)],
                )

        if args.write:
            for reg in args.write:
                parts = reg.split(":")

                if len(parts) < 2:
                    dtype = "uint32"
                else:
                    dtype = parts[1]

                offset, val = parts[0].split("=")

                val = float(ast.literal_eval(val))
                offset = int(offset, 0)

                await noa.setup_write_register(reg, offset, dtype)
                await noa.write_register(reg, val)

        if args.stream_in:
            data = np.loadtxt(
                sys.stdin if args.stream_in == "-" else args.stream_in, delimiter=","
            )
            await noa.stream_in.write(data, dtype=args.stream_in_dtype)

        if args.daq_output:
            if not args.daq_channels:
                raise ValueError("--daq-channels is required when using --daq-output")

            parsed_channels = []
            for arg in args.daq_channels:
                parts = arg.split(":")
                ch_idx = int(parts[0])
                dtype = parts[1] if len(parts) > 1 else "uint32"
                parsed_channels.append((ch_idx, dtype))

            try:
                await noa.daq.setup_data(
                    window_size=args.daq_window,
                    decimation=args.daq_decimation,
                    delay=args.daq_delay,
                )

                for ch_idx, dtype in parsed_channels:
                    await noa.daq.enable_channel(ch_idx, dtype=dtype)

                trigger = DaqTrigger(
                    kind=TriggerKind[args.daq_trigger],
                    channel=args.daq_trigger_ch,
                    a=args.daq_trigger_a,
                    b=args.daq_trigger_b,
                    threshold=args.daq_trigger_threshold,
                    hysteresis=args.daq_trigger_hysteresis,
                )
                await noa.daq.trigger(trigger)

                all_collected_data = []
                for i in range(args.daq_nb_windows):
                    log.info(f"Capturing window {i+1}/{args.daq_nb_windows}...")
                    window_data = []
                    for ch_idx, dtype in parsed_channels:
                        data = await noa.daq.read(ch_idx)
                        window_data.append(data)
                    all_collected_data.append(np.column_stack(window_data))

                final_data = np.vstack(all_collected_data)

                if args.daq_output == "-":
                    np.savetxt(sys.stdout, final_data, delimiter=",")
                else:
                    header = ",".join([f"CH{c[0]}" for c in parsed_channels])
                    np.savetxt(
                        args.daq_output, final_data, delimiter=",", header=header
                    )

                log.info(f"DAQ capture complete. Total samples: {len(final_data)}")
            finally:
                await noa.daq.reset()

        if args.read:
            for reg in args.read:
                parts = reg.split(":")
                offset = int(parts[0], 0)  # convert from any base
                if len(parts) < 2:
                    dtype = "uint32"
                else:
                    dtype = parts[1]

                await noa.setup_read_register(reg, offset, dtype=dtype)
                val = noa.read_register(reg)

                log.info(f"Read register {reg} ({dtype}) => {val}")
                print(val)

    finally:
        if args.disconnect:
            await noa.disconnect()


if __name__ == "__main__":
    asyncio.run(_main())

def _main_entry():
    asyncio.run(_main())
