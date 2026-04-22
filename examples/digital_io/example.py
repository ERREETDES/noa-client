import asyncio

from noa.noa import Noa
from noa.digital_io import PinMap

previous = None
bit_flips = None

async def run(addr, bit, hwh, logger):
    async with Noa(addr, logger) as noa:
        # The example bitstream has 3 digital outputs and one digital input:
        # - Output 0, 1 bit,   constant zero
        # - Output 1, 1 bit,   constant one
        # - Output 2, 32 bits, 20MHz 32-bit up-counter
        #
        # - Input  0, 32 bits, sampled by a read register at offset 0x100
        ZERO = 0
        ONE = 1
        COUNTER = 2
        IN0 = 0
    
        # To run this example, physically connect these pins together in a loopback configuration:
        # - DB 16 and DB 31
        # - DB 17 and DB 30
        # - DB 18 and DB 29
        # - DB 19 and DB 28

        await noa.load_bitstream(bit, hwh)
        await noa.setup_read_register("IN0", 0x10c, dtype="int32")

        
        # Setup digital io port DB
        # Output Constant Zero => pin 16  => pin 31 => IN0 bit 0
        # Output Constant One  => pin 17  => pin 30 => IN0 bit 1
        # Output Counter bit 20 => pin 18 => pin 29 => IN0 bit 2 (~10 hz)
        # Output Counter bit 22 => pin 19 => pin 28 => IN0 bit 3 (~2.5 hz)
        await noa.DB.setup(
            inputs=[
                PinMap(sig=IN0, bit=0, pin=31),
                PinMap(sig=IN0, bit=1, pin=30),
                PinMap(sig=IN0, bit=2, pin=29),
                PinMap(sig=IN0, bit=3, pin=28)
            ],
            outputs=[
                PinMap(sig=ZERO,    bit=0, pin=16),
                PinMap(sig=ONE,     bit=0, pin=17),
                PinMap(sig=COUNTER, bit=20, pin=18),
                PinMap(sig=COUNTER, bit=22, pin=19)
            ],
        )

        global previous
        global bit_flips
        previous = 0b10
        bit_flips = [0]*32

        async def count_bit_flips(name, value):
            global previous
            changed = previous ^ value
            previous = value

            for i in range(32):
                if changed & (1 << i):
                    bit_flips[i] += 1 # type: ignore


            print(f"{name}: ", f"{value:032b}")

        await noa.setup_read_register("IN0", 0x100, cb=count_bit_flips)

        t = 5
        await asyncio.sleep(t)

        # Validate number of bit flips
        # 2 flips per hz, plus or minus 10% for asynchronous register aliasing
        expected_hz = [0.0]*32
        expected_hz[3] = 2.5
        expected_hz[2] = 10

        error = False
        for i, (hz, flips) in enumerate(zip(expected_hz, bit_flips)):
            if hz == 0.0:
                if flips != 0:
                    print(f"IN0 bit {i} flipped {flips} time(s), expected zero!")
                    error = True
                    continue
            else:
                if flips > 2.2*hz*t or flips < 1.8*hz*t:
                    print(f"IN0 bit {i} flipped {flips} time(s), expected around {2*hz*t}!")
                    error = True
            
        assert not error, f"{bit_flips}"
        print("Success!")

if __name__ == "__main__":
    import sys

    addr = sys.argv[1]
    bit = "examples/digital_io/design_1_wrapper.bit"
    hwh = "examples/digital_io/design_1.hwh"

    asyncio.run(run(addr, bit, hwh, logger=None))