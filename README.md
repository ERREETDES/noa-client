# NOA Python Client

Programmatic interface for NOA hardware.

## Python API Examples
Example usage of the python API can be found in the `examples/` directory:
| Name | Description |
| :--- | :--- |
| `registers` | Register operations |
| `analog_out` | Setup analog outputs |
| `digital_io` | Setup digital IOs |
| `stream_in` | Write to a stream input |
| `daq` | Use the DAQ system |

## CLI Usage
The noa module can be run directly to run a built-in example or for manual operations.

`python -m noa.noa <addr> [options]`

### General
- `<addr>`: Device address (e.g., `arch1-00001.local` or `192.168.1.12`).
- `-v`: Verbose mode
- `--device-info`: Print device information
- `--disconnect`: Force disconnect. Used in manual operation or to recover from a crash.

### Examples
- `--example <name>`: Run a built-in example (`analog_out`, `daq`, `digital_io`, `registers`, `stream_in`).

### Manual operations

run `python -m noa.noa --help` for a list of manual operations. They can be combined together in a single command.