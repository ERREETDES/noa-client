import asyncio
from pathlib import Path

from noa.noa import Noa
from noa.daq import DaqTrigger, TriggerKind

from matplotlib import pyplot as plt
import numpy as np

fig, ax = plt.subplots()
lines = {}

def setup_plot():
    plt.ion()
    plt.show()

async def update_plot(channel, data):
    x_values = range(len(data))

    if channel not in lines:
        # Initialize the line. 'lines' returns a list, so we take the first element [0]
        lines[channel], = ax.plot(x_values, data, label=f"Channel {channel}")
        ax.relim()
        ax.autoscale_view()
        fig.legend(loc="upper right")

    line = lines[channel]

    line.set_ydata(data)
    fig.canvas.draw_idle()
    plt.pause(0.01)


async def run(addr, bit, hwh, logger):
    async with Noa(addr, logger) as noa:
        # The example bitstream generates a 3-phase sine wave through its DAQ  
        # Each phase is output onto two consecutive channels (phase 0 : channels 0 and 1, phase 1: channels 2 and 3, etc.)
        # Channels 0, 2, 4 are displayed using matplotlib as an example of callback mode
        # Channels 1, 3, 5 are used in queue mode to write CSV files.
        await noa.load_bitstream(bit, hwh)

        # Setup data acquisition
        await noa.daq.setup_data(window_size=10000, decimation=1, delay=0)

        # Enable channels in callback mode (callback is called on every new data frame)
        setup_plot()
        await noa.daq.enable_channel(0, dtype="fixdt(1,32,29)", cb=update_plot)
        await noa.daq.enable_channel(2, dtype="fixdt(1,32,29)", cb=update_plot)
        await noa.daq.enable_channel(4, dtype="fixdt(1,32,29)", cb=update_plot)

        # Enable 3 channels in queue mode (no callback, buffered reads through daq.read)
        await noa.daq.enable_channel(1, dtype="fixdt(1,32,29)")
        await noa.daq.enable_channel(3, dtype="fixdt(1,32,29)")
        await noa.daq.enable_channel(5, dtype="fixdt(1,32,29)")

        # Setup trigger
        # warning : DAQ trigger logic treats signals as int32s
        await noa.daq.trigger(DaqTrigger(kind=TriggerKind.Immediate))
        #await noa.daq.trigger(DaqTrigger(kind=TriggerKind.Between, channel=0, a=-1000, b=1000))
        #await noa.daq.trigger(DaqTrigger(kind=TriggerKind.GreaterThan, channel=0, a=100000))
        #await noa.daq.trigger(DaqTrigger(kind=TriggerKind.RisingEdge, channel=0, threshold=0, hysteresis=10)) # plot does not move because the signal is periodic

        # Use the queue mode channels to write 1s of data to disk

        # Acquire data for 1s
        await asyncio.sleep(1)

        # Stop acquisition
        await noa.daq.disable_channel(1)
        await noa.daq.disable_channel(3)
        await noa.daq.disable_channel(5)

        # Save each frame to a csv file
        for ch in [1, 3, 5]:
            dir = Path(bit).parent
            n = 0
            while noa.daq.read_ready(ch):
                data = await noa.daq.read(ch)
                print(dir/f"channel{ch}_frame{n}.csv")
                np.savetxt(dir/f"channel{ch}_frame{n}.csv", data, delimiter=",")
                n += 1
        
        # Stay alive to keep displaying plot
        while 1:
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    import sys
    import logging

    addr = sys.argv[1]
    bit = "examples/daq/design_1_wrapper.bit"
    hwh = "examples/daq/design_1.hwh"

    asyncio.run(run(addr, bit, hwh, logger=None))