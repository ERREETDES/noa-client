from copy import copy
from enum import Enum
import json
from typing import List

from attrs import define

MAX_SIGNALS = 8


@define
class PortMap:
    signal_offset: int
    banks: list[list[int]]

ARCH1_DA = PortMap(
    signal_offset = 32,
    banks = [
        [0,  1,  2,  3,  16, 17, 18, 19],
        [4,  5,  6,  7],
        [8,  9,  10, 11],
        [12, 13, 14, 15],
    ]
)

ARCH1_DB = PortMap(
    signal_offset=0,
    banks = [
        [0,  1,  2,  3,  16, 17, 18, 19],
        [4,  5,  6,  7,  20, 21, 22, 23],
        [8,  9,  10, 11, 24, 25, 26, 27],
        [12, 13, 14, 15, 28, 29, 30, 31],
    ]
)

class Direction(str, Enum):
    Input = "INPUT"
    Output = "OUTPUT"

class Voltage(str, Enum):
    D3V3 = "D3V3"
    D5V0 = "D5V0"

@define
class PinMap:
    sig: int
    bit: int
    pin: int
    v: Voltage = Voltage.D3V3

class DIOPort:
    def __init__(self, noa, name, port: PortMap, log) -> None:
        self._noa = noa
        self._name = name
        self._port = port
        self._log = log.getChild(name)

        self._nb_banks = len(self._port.banks)
        self._nb_pins = sum(len(b) for b in self._port.banks)

    async def setup(self, inputs: List[PinMap], outputs: List[PinMap]):
        """ Setup the digital IO port """
        self._log.debug(f"setup: inputs={inputs}, outputs={outputs}")
        self._bank_direction = [None]*self._nb_banks
        self._bank_voltage = [None]*self._nb_banks
        self._inputs = copy(inputs)
        self._outputs = copy(outputs)

        await self._setup_port(enable=False)

        for pin in range(self._nb_pins):
            # Set all pins to hi-z
            await self._map_signal_unchecked(None, 0, pin, Direction.Input)

        for out in outputs:
            await self._map_signal(
                pin=out.pin,
                signal=out.sig,
                bit=out.bit,
                voltage=out.v,
                direction=Direction.Output,
            )

        for inp in inputs:
            await self._map_signal(
                pin=inp.pin,
                signal=inp.sig,
                bit=inp.bit,
                voltage=inp.v,
                direction=Direction.Input,
            )

        await self._setup_port()

    async def _setup_port(self, enable=True):
        self._log.debug(f"_setup_port: enable={enable}")
        opts = {}
        opts["enable"] = enable
        opts["addr"] = self._name

        if enable:
            direction = [
                d if d is not None else Direction.Input
                for d in self._bank_direction
            ]

            voltage = [
                v if v is not None else Voltage.D5V0
                for v in self._bank_voltage
            ]

            opts["dir"] = direction
            opts["voltage"] = voltage

        await self._noa._req_expect_ok(self._noa._ov_prefix+".setup-dio", json.dumps(opts).encode())

    async def _map_signal(self, pin, signal, bit, voltage, direction):
        self._log.debug(f"map signal: pin={pin}, signal={signal}, bit={bit}, voltage={voltage}, direction={direction}")
        bank = self._find_bank(pin)
        bank_pins = self._port.banks[bank]
        bank_voltage = self._bank_voltage[bank]

        if bank_voltage is None:
            self._bank_voltage[bank] = voltage
            self._bank_direction[bank] = direction
            bank_voltage = voltage

        if self._bank_direction[bank] != direction:
            raise ValueError(f"Pin {self._name} {pin} is in the same bank as pins {bank_pins} which are configured as {self._bank_direction[bank]}.")

        if bank_voltage != voltage:
            raise ValueError(f"Pin {self._name} {pin} is in the same bank as pins {bank_pins} which is configured with a different voltage ({bank_voltage})")
        
        await self._map_signal_unchecked(signal, bit, pin, direction)
    
    
    async def _map_signal_unchecked(self, signal, bit, pin, direction):
        pin_hw = pin + self._port.signal_offset

        if signal is None:
            if direction == Direction.Input:
                value = "HIZ"
            else:
                value = "ZERO"
        else:
            sig_idx = signal*32 + bit
            if direction == Direction.Input:
                value = f"IN{sig_idx}"
            else:
                value = f"OUT{sig_idx}"

        self._log.debug(f"pin={pin} (hw={pin_hw}), value={value}")
        await self._noa._setparam(f"matlab-dio.pins.{pin_hw}", value.encode())

    def _find_bank(self, pin):
        for i, bank in enumerate(self._port.banks):
            if pin in bank:
                return i
        
        raise ValueError(f"Pin {pin} not in port {self._name}") 