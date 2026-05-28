import queue
import multiprocessing

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

class Graph:
    def __init__(self):
        self.q = multiprocessing.Queue()
        self.current_data = {}
        self.curves = {}
        self.updated_channels = set()
        self.process = None
        self.app = None
        self._stopping = multiprocessing.Event()

    def on_data(self, channel_idx, data):
        self.q.put((int(channel_idx), data))

    def show(self):
        if self.process is not None and self.process.is_alive():
            return

        self._stopping.clear()
        self.process = None
        process = multiprocessing.Process(target=self._run_loop, daemon=True)
        process.start()
        self.process = process

    def stop(self):
        if self.process is None:
            return

        self._stopping.set()
        self.process.join()
        self.process = None

    def _run_loop(self):
        pg.setConfigOptions(antialias=True)

        self.app = pg.mkQApp()
        self.window = pg.PlotWidget(title="NOA DAQ")
        self.window.resize(1000, 600)
        self.window.setWindowTitle("NOA DAQ")

        self.plot = self.window.getPlotItem()
        self.plot.setLabel("bottom", "Sample")
        self.plot.setLabel("left", "Value")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend()

        self.window.show()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_plot)
        self.timer.start(0)

        try:
            if not self._stopping.is_set():
                pg.exec()
        finally:
            self.timer.stop()
            self.window.close()
            self.timer = None
            self.window = None
            self.plot = None
            self.curves = {}
            self.app = None
            self.process = None

    def _update_plot(self):
        if self._stopping.is_set():
            self.app.quit()
            return

        new_channel_seen = False
        try:
            while 1:
                index, data = self.q.get_nowait()
                new_channel = index not in self.current_data
                self.current_data[index] = data
                if new_channel:
                    new_channel_seen = True
                else:
                    self.updated_channels.add(index)
        except queue.Empty:
            pass

        all_channels_updated = self.updated_channels and self.updated_channels == set(self.current_data)
        if all_channels_updated:
            self.updated_channels.clear()

        if not new_channel_seen and not all_channels_updated:
            return
    
        for index, data in self.current_data.items():
            if index not in self.curves:
                self.curves[index] = self.plot.plot(
                    pen=pg.mkPen(pg.intColor(abs(index), hues=24), width=2),
                    name=f"Channel {index}",
                )

            self.curves[index].setData(data)
