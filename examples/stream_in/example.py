import numpy as np

from noa.noa import Noa

async def run(addr, bit, hwh, logger):
    async with Noa(addr, logger) as noa:
        # The example bitstream read a string input. It calculates the sum of all words into register  0x104 and the number of words in register 0x108.
        # The register 0x100 acts as an active-high reset.

        await noa.load_bitstream(bit, hwh)
        await noa.setup_read_register("sum", 0x104)
        await noa.setup_read_register("count", 0x108)
        await noa.setup_write_register("reset", 0x100, dtype="logical")

        await noa.stream_in.write(np.arange(100, dtype=np.uint32))

        assert noa.read_register("sum") == sum(range(int(100)))
        assert noa.read_register("count") == 100

        await noa.write_register("reset", True)
        await noa.write_register("reset", False)

        await noa.stream_in.write(np.ones(int(1e6), dtype=np.uint32))
        assert noa.read_register("sum") == int(1e6)
        assert noa.read_register("count") == int(1e6)

        print("Success!")
        