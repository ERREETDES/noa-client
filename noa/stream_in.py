from .typecast import Typecast


class StreamIn:
    def __init__(self, noa, name, log) -> None:
        self._noa = noa
        self._name = name
        self._prefix = noa._ov_prefix+"."+name
        self._log = log.getChild(name)
    
    async def write_chunk(self, data: bytes, last=True):
        """ Write a single chunk of raw bytes to the stream. data must be smaller than 1M bytes and a multiple of 4"""
        self._log.debug(f"write_chunk: len={len(data)} last={last}")

        assert len(data) <= 1e6
        assert len(data) % 4 == 0

        data = bytes(data)

        if last:
            await self._noa._req_expect_ok(self._prefix+".write-last", data)
        else:
            await self._noa._req_expect_ok(self._prefix+".write", data)
    
    async def write(self, buf, dtype="uint32"):
        """ Write an array of words to the stream. dtype determines how each element is converted to a 32-bit word."""
        self._log.debug(f"write: len={len(buf)} dtype={dtype}")
        CHUNK_SIZE = int(1e6)
        buf = Typecast(dtype).to_bytes(buf)

        idx = 0
        l = len(buf)

        while idx < l:
            sz = min(CHUNK_SIZE, l - idx)
            last = sz + idx == l

            await self.write_chunk(buf[idx:idx+sz], last=last)
            idx += sz