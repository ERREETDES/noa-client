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

run `python -m noa.noa --help` for a list of manual operations or the scripts directory for example usage. They can be combined together in a single command.