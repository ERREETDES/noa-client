import asyncio

from noa.noa import Noa

async def run(addr, bit, hwh, logger):
    async with Noa(addr, logger) as noa:
        # The example bitstream has two write registers, `A` and `B`
        # The value of `A` + `B` is output to its read register, `sum`
        await noa.load_bitstream(bit, hwh)

        # Read registers are updated asynchronously when the value changes
        # an optional callback can be specified to avoid polling for updates.
        sums = []
        async def callback(name, value):
            print("Updated sum", value)
            sums.append(value)

        await noa.setup_write_register("A", 0x104, dtype="int32")
        await noa.setup_write_register("B", 0x108, dtype="int32")
        await noa.setup_read_register("sum", 0x10c, dtype="int32", cb=callback)

        # Manually read register value
        initial_value = noa.read_register("sum")
        print("Initial value:", initial_value)

        # Write register values, the sum list is updated asynchronously by the callback
        await noa.write_register("A", 100)
        await noa.write_register("B", 120)
        await asyncio.sleep(0.1)

        await noa.write_register("A", 110)
        await asyncio.sleep(0.1)

        await noa.write_register("A", 120)
        await asyncio.sleep(0.1)

        await noa.write_register("A", 130)
        await asyncio.sleep(0.1)

        assert(sums == [0, 220, 230, 240, 250])
        print("Success!")

if __name__ == "__main__":
    import sys
    import logging

    addr = sys.argv[1]
    bit = "examples/registers/design_1_wrapper.bit"
    hwh = "examples/registers/design_1.hwh"

    asyncio.run(run(addr, bit, hwh, logger=None))