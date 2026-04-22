import numpy as np
import re

class Typecast:
    """
    Handles conversion between bytes (as 32-bit words) and various target dtypes. This is used to translate to and from HDL Coder's binary representation
    of Matlab datatypes.
    """
    def __init__(self, dtype: str):
        self.dtype_str = dtype
        self._setup(dtype)

    def _setup(self, dtype_str: str):
        dt = dtype_str.strip().lower()
        
        self._is_fixint = False
        if dt == 'int8':
            self._from_u32 = lambda v: v.astype(np.uint8).view(np.int8)
            self._to_u32 = lambda v: v.view(np.uint8).astype(np.uint32)
        elif dt == 'int16':
            self._from_float = lambda v: v.astype(np.int16)
            self._from_u32 = lambda v: v.astype(np.uint16).view(np.int16)
            self._to_u32 = lambda v: v.view(np.uint16).astype(np.uint32)
        elif dt == 'int32':
            self._from_u32 = lambda v: v.view(np.int32)
            self._to_u32 = lambda v: v.view(np.uint32)
        elif dt == 'uint8':
            self._from_u32 = lambda v: v.astype(np.uint8)
            self._to_u32 = lambda v: v.astype(np.uint32)
        elif dt == 'uint16':
            self._from_u32 = lambda v: v.astype(np.uint16)
            self._to_u32 = lambda v: v.astype(np.uint32)
        elif dt == 'uint32':
            self._from_u32 = lambda v: v.astype(np.uint32)
            self._to_u32 = lambda v: v.astype(np.uint32)
        elif dt in ('single', 'float32'):
            self._from_u32 = lambda v: v.view(np.float32)
            self._to_u32 = lambda v: v.view(np.uint32)
        elif dt in ('logical', 'boolean'):
            self._from_u32 = lambda v: v != 0
            self._to_u32 = lambda v: v.astype(np.uint32)
        elif dt.startswith('fixdt'):
            self._is_fixint = True
            self._setup_fixdt(dt)
        else:
            raise ValueError(f"Unsupported target type: {dtype_str}")

    def _setup_fixdt(self, dt: str):
        # Match fixdt(signed, wordlength, fractionlength)
        m = re.match(r"fixdt\s*\(\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.-]+))?\s*\)", dt)
        if m:
            signed = int(m.group(1)) != 0
            wl = int(m.group(2))
            fl = float(m.group(3)) if m.group(3) is not None else 0.0
            
            mask = (1 << wl) - 1
            scale = 2.0**(-fl)
            inv_scale = 2.0**fl

            def from_u32(v):
                # Extract wl bits
                val = v & mask
                if signed:
                    # Sign extend from wl bits to 32 bits using arithmetic shift
                    shift = 32 - wl
                    val = (val << shift).view(np.int32) >> shift
                return val.astype(np.float64) * scale

            def to_u32(v):
                # Quantize float to integer, round to nearest, and mask to wl bits
                val = np.round(np.asarray(v) * inv_scale).astype(np.int64)
                return (val & mask).astype(np.uint32)

            self._from_u32 = from_u32
            self._to_u32 = to_u32
        else:
            # Match fixdt('typename') alias
            m_str = re.match(r"fixdt\s*\(\s*['\"](\w+)['\"]\s*\)", dt)
            if m_str:
                self._setup(m_str.group(1))
            else:
                raise ValueError(f"Invalid fixdt specification: {dt}")

    def from_bytes(self, data: bytes) -> np.ndarray:
        """
        Converts a bytes object (multiple of 4 bytes) into a numpy array of the target type.
        Each 32-bit word in the input represents one element.
        """
        if not data:
            return np.array([])
        u32 = np.frombuffer(data, dtype='<u4')
        return self._from_u32(u32)

    def to_bytes(self, arr) -> bytes:
        """
        Converts a numpy array or list into a bytes object.
        Each element is packed into a 32-bit word in the resulting byte stream.
        """
        if not isinstance(arr, np.ndarray):
            arr = np.array(arr)
        u32 = self._to_u32(arr)
        return u32.tobytes()
    
    def from_float(self, f: float):
        if self._is_fixint:
            dtype = np.float64
        else:
            dtype = self._from_u32(np.zeros(4)).dtype

        return np.atleast_1d([f]).astype(dtype) # type: ignore