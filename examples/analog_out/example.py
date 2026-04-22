import asyncio
from noa.noa import Noa

async def run(addr, bit, hwh, logger):

    async with Noa(addr, logger) as noa:
        # The example bitstream outputs a 3-phase sine wave to its analog outputs
        await noa.load_bitstream(bit, hwh)
        await noa.enable_analog_outputs()

        await noa.A0.setup(signal=0, signal_range=[-1, 1], voltage_range=[-5, 5])
        await noa.A1.setup(signal=1, signal_range=[-1, 1], voltage_range=[-5, 5])
        await noa.A2.setup(signal=2, signal_range=[-1, 1], voltage_range=[-5, 5])

        await asyncio.sleep(5)

        # Map the output signal the  0V-3.3V range
        await noa.A0.setup(signal=0, signal_range=[-1, 1], voltage_range=[0, 3.3])
        await noa.A1.setup(signal=1, signal_range=[-1, 1], voltage_range=[0, 3.3])
        await noa.A2.setup(signal=2, signal_range=[-1, 1], voltage_range=[0, 3.3])

        await asyncio.sleep(5)

        # Disable output
        await noa.enable_analog_outputs(A0_to_A3=False, A4_to_A7=False, A8_to_A11=False)

if __name__ == "__main__":
    import sys
    import logging

    addr = sys.argv[1]
    bit = "examples/analog_out/design_1_wrapper.bit"
    hwh = "examples/analog_out/design_1.hwh"

    asyncio.run(run(addr, bit, hwh, logger=None))