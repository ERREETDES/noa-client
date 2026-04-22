from copy import copy
from enum import Enum
import json
from math import ceil, log2
from typing import List

from attrs import define


class Scale(str, Enum):
    PLUS_MINUS_5V0 = "PLUS_MINUS_5V0"
    PLUS_MINUS_1V25 = "PLUS_MINUS_1V25"


class Aout:
    def __init__(self, noa, offset, log) -> None:
        self._noa = noa
        self._offset = offset
        self._log = log.getChild(f"A{offset}")

    async def setup(self, signal, signal_range, voltage_range):
        """ Setup analog output port. signal_range must correspond the the signal range specified in the AnalogOut block."""

        self._log.debug(
            f"signal={signal} signal_range={signal_range} voltage_range={voltage_range}"
        )
        nb_bits = 32

        assert len(signal_range) == 2
        assert len(voltage_range) == 2

        signal_min = float(signal_range[0])
        signal_max = float(signal_range[1])
        voltage_min = float(voltage_range[0])
        voltage_max = float(voltage_range[1])

        assert signal_min <= signal_max
        assert voltage_min >= -5
        assert voltage_max <= 5
        assert voltage_min <= voltage_max

        nb_fract = ceil(nb_bits - log2(max(abs(signal_max), abs(signal_min))) - 1)

        signal_range = (2 ** (nb_bits) - 1) / (2**nb_fract)

        signal_actual_range = signal_max - signal_min
        voltage_range = voltage_max - voltage_min

        gain = voltage_range * (signal_range / signal_actual_range)

        if voltage_min < -1.25 or voltage_max > 1.25:
            scale = Scale.PLUS_MINUS_5V0
            gv = 5
        else:
            scale = Scale.PLUS_MINUS_1V25
            gv = 1.25

        gain = gain / gv
        offset = voltage_min / gv - signal_min * gain / (signal_range)

        self._log.debug(f"scale={scale} gain={gain} offset={offset}")

        await self._noa._req_expect_ok(
            f"{self._noa._ov_prefix}.A{self._offset}.setup",
            json.dumps(
                {
                    "scale": scale,
                    "gain": 1,
                    "offset": 0,
                }
            ).encode(),
        )

        await self._noa._setparam(
            f"matlab-aout.A{self._offset}.signal", f"{signal}".encode()
        )

        await self._noa._setparam(
            f"matlab-aout.A{self._offset}.gain", f"{gain/256}".encode()
        )

        await self._noa._setparam(
            f"matlab-aout.A{self._offset}.offset", f"{offset}".encode()
        )
