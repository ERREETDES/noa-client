# NOA Python Client

Python client for the NOA platform. See [docs.rexys.io](https://docs.rexys.io) for more information.

## Python API Examples
Example usage of the python API can be found in the `examples/` directory:
| Name | Description |
| :--- | :--- |
| `registers` | Register operations |
| `analog_out` | Setup analog outputs |
| `digital_io` | Setup digital IOs |
| `stream_in` | Write to a stream input |
| `daq` | Use the DAQ system |

## CLI
The noa module can be run directly to execute a built-in example or manual operations.

`python -m noa.noa <addr> [options]`

### General
- `<addr>`: Device address (e.g., `arch1-00001.local` or `192.168.1.12`).
- `-v`: Verbose mode
- `--device-info`: Print device information
- `--disconnect`: Force disconnect. Used in manual operation or to recover from a crash.

### Examples
- `--example <name>`: Run a built-in example (`analog_out`, `daq`, `digital_io`, `registers`, `stream_in`).

### Manual operations
Multiple operations can specified in the same command.

```
  --bit path            load a bitstream file
  --hwh path            specify a different hwh file
  --device-info         Print device information
  --digital-inputs signal:bit:port:pin [signal:bit:port:pin ...]
                        Configure digital inputs (1:0:DA:16 1:1:DB:32)
  --digital-outputs signal:bit:port:pin [signal:bit:port:pin ...]
                        Configure digital outputs
  --analog-outputs signal:port:sigmin:sigmax:vmin:vmax [signal:port:sigmin:sigmax:vmin:vmax ...]
                        Configure analog outputs (0:A2:-1:1:-5:5 1:A3:0:1:0:5)
  --read offset [offset ...]
                        read registers to stdout (i.e. --read 0x100 0x104 "0x10C:fixdt(1,16,5)"
  --write expr [expr ...]
                        write registers (i.e. --write 0x100=0 0x104=1:int8
  --stream-in path      stream data from a file (or '-' for stdin)
  --stream-in-dtype dtype
                        data type for streaming (default: uint32)
  --daq-output path     Save DAQ data to a CSV file (or '-' for stdout)
  --daq-channels ch[:dtype] [ch[:dtype] ...]
                        DAQ channels to record (e.g. 0:fixdt(1,16,5) 1)
  --daq-window DAQ_WINDOW
                        DAQ window size (default: 1000)
  --daq-decimation DAQ_DECIMATION
                        DAQ decimation (default: 1)
  --daq-delay DAQ_DELAY
                        DAQ delay (default: 0)
  --daq-nb-windows DAQ_NB_WINDOWS
                        Number of windows to record (default: 1)
  --daq-trigger {Immediate,RisingEdge,FallingEdge,BothEdges,TriggerIn,EqualTo,GreaterThan,LessThan,Between}
                        Trigger kind (default: Immediate)
  --daq-trigger-ch DAQ_TRIGGER_CH
                        Trigger channel index
  --daq-trigger-a DAQ_TRIGGER_A
                        Trigger 'a' parameter
  --daq-trigger-b DAQ_TRIGGER_B
                        Trigger 'b' parameter
  --daq-trigger-threshold DAQ_TRIGGER_THRESHOLD
                        Trigger threshold
  --daq-trigger-hysteresis DAQ_TRIGGER_HYSTERESIS
                        Trigger hysteresis
  --disconnect          disconnects from the target
```
