# SPDX-License-Identifier: GPL-3.0-or-later
"""U3D bit stream: plain values, the adaptive arithmetic coder and the dynamic
histogram, ported from the U3D Sample Software (CIFXBitStreamX.cpp,
IFXHistogramDynamic.cpp; Apache-2.0, see THIRD-PARTY.md).

Conventions (ECMA-363 section 10):
- the stream is a sequence of little-endian U32 words, bits filled LSB first;
- while the coder is in its initial state (high 0xFFFF, low 0, no underflow)
  plain U8 values are written as bytes; afterwards every plain byte goes
  through the static context ``STATIC_FULL + 256`` as ``swap8(byte) + 1``;
- ``write_cu32(context, value)`` codes ``value + 1``: contexts above
  ``STATIC_FULL`` are uniform (``context - STATIC_FULL`` symbols), contexts
  from 1 to ``STATIC_FULL`` are adaptive histograms with symbol 0 as the
  escape, context 0 and contexts at or above ``MAX_RANGE`` are plain.
"""
from __future__ import annotations

import struct

STATIC_FULL = 0x00000400
MAX_RANGE = STATIC_FULL + 0x00003FFF
_HALF = 0x8000
_QUARTER = 0x4000
_HALF_MASK = 0x80008000
_NOT_HALF = 0x7FFF7FFF
_QUARTER_MASK = 0x40004000
_NOT_3Q = 0x3FFF3FFF
_SWAP4 = (0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15)
_ELEPHANT = 0x1FFF


def swap8(v: int) -> int:
    """Reverse the eight least significant bits."""
    return (_SWAP4[v & 0xF] << 4) | _SWAP4[(v >> 4) & 0xF]


class Histogram:
    """IFXHistogramDynamic: symbol counts with a block-of-four suffix-sum
    table; symbol 0 is the escape and starts with count 1."""

    def __init__(self, elephant: int = _ELEPHANT) -> None:
        self.n = 100
        self.count = [0] * self.n
        self.cum4 = [0] * ((self.n >> 2) + 1)
        self.count[0] = 1
        self.cum4[0] = 1
        self.elephant = elephant

    def freq(self, s: int) -> int:
        return self.count[s] if s < self.n else 0

    def cum(self, s: int) -> int:
        """Cumulative frequency of every symbol below ``s``."""
        if s <= self.n:
            c = self.cum4[0] - self.cum4[s >> 2]
            for i in range(s & ~3, s):
                c += self.count[i]
            return c
        return self.cum4[0]

    def total(self) -> int:
        return self.cum4[0]

    def symbol_from_freq(self, f: int) -> int:
        """The largest symbol whose cumulative frequency is at most ``f``."""
        if f >= self.cum4[0]:
            return 0
        lo, hi = 0, self.n >> 2
        total = self.cum4[0]
        while hi - lo > 4:
            mid = (lo + lo + lo + hi) >> 2
            if f >= total - self.cum4[mid]:
                lo = mid
            else:
                hi = mid
        lo <<= 2
        hi = (hi << 2) + 3
        while hi - lo > 4:
            mid = (lo + hi) // 2
            if f >= self.cum(mid):
                lo = mid
            else:
                hi = mid
        s = 0
        for i in range(lo, hi + 1):
            if f >= self.cum(i):
                s = i
            else:
                break
        return s

    def add(self, s: int) -> None:
        if s > 0xFFFF:
            return
        if self.cum4[0] >= self.elephant:
            self.cum4 = [0] * ((self.n >> 2) + 1)
            for i in range(self.n, 0, -1):
                self.count[i - 1] >>= 1
                self.cum4[(i - 1) >> 2] += self.count[i - 1]
            for i in range(self.n >> 2, 0, -1):
                self.cum4[i - 1] += self.cum4[i]
            self.count[0] += 1
            self.cum4[0] += 1
        if s >= self.n:
            old_n = self.n
            self.n = s + 100
            self.count += [0] * (self.n - old_n)
            self.cum4 += [0] * (((self.n >> 2) + 1) - len(self.cum4))
        self.count[s] += 1
        for i in range((s >> 2) + 1):
            self.cum4[i] += 1


class _Coder:
    """State shared by the writer and the reader."""

    def __init__(self) -> None:
        self.pos = 0
        self.off = 0
        self.high = 0xFFFF
        self.low = 0
        self.underflow = 0
        self.hist: dict[int, Histogram] = {}

    def bitcount(self) -> int:
        return (self.pos << 5) + self.off

    def _initial(self) -> bool:
        return self.high == 0xFFFF and self.low == 0 and self.underflow == 0

    def _histogram(self, context: int) -> Histogram:
        h = self.hist.get(context)
        if h is None:
            h = self.hist[context] = Histogram()
        return h


class BitWriter(_Coder):
    def __init__(self) -> None:
        super().__init__()
        self.w = [0, 0, 0]
        self.compressed = False

    # ---- raw bits -----------------------------------------------------------
    def _ensure(self) -> None:
        while len(self.w) < self.pos + 3:
            self.w.append(0)

    def _wrap(self) -> None:
        while self.off >= 32:
            self.off -= 32
            self.pos += 1
            self._ensure()

    def write_bit(self, bit: int) -> None:
        self._ensure()
        self.w[self.pos] |= (bit & 1) << self.off
        self.off += 1
        self._wrap()

    def _put_bits(self, value: int, nbits: int) -> None:
        self._ensure()
        self.w[self.pos] |= (value << self.off) & 0xFFFFFFFF
        if self.off + nbits > 32:
            self.w[self.pos + 1] |= value >> (32 - self.off)
        self.off += nbits
        self._wrap()

    # ---- arithmetic coder ---------------------------------------------------
    def _narrow_and_renorm(self, total: int, vcum: int, vfreq: int) -> None:
        rng = self.high + 1 - self.low
        self.high = self.low - 1 + rng * (vcum + vfreq) // total
        self.low = self.low + rng * vcum // total
        bit = self.low >> 15
        while (self.high & _HALF) == (self.low & _HALF):
            self.high &= 0x7FFF
            self.high = self.high + self.high + 1
            self.write_bit(bit)
            while self.underflow > 0:
                self.underflow -= 1
                self.write_bit((~bit) & 1)
            self.low &= 0x7FFF
            self.low += self.low
            bit = self.low >> 15
        while (self.high & _QUARTER) == 0 and (self.low & _QUARTER) == _QUARTER:
            self.high &= 0x7FFF
            self.high <<= 1
            self.low <<= 1
            self.high |= _HALF | 1
            self.low &= 0x7FFF
            self.underflow += 1

    def _write_static(self, context: int, symbol: int) -> bool:
        nsym = context - STATIC_FULL
        if symbol == 0 or symbol > nsym:
            raise ValueError(f"symbol {symbol} outside static context of {nsym}")
        self._narrow_and_renorm(nsym, symbol - 1, 1)
        return False

    def _write_dynamic(self, context: int, symbol: int) -> bool:
        h = self._histogram(context)
        vfreq = h.freq(symbol)
        if vfreq == 0:
            symbol = 0
            vfreq = h.freq(0)
        vcum = h.cum(symbol)
        total = h.total()
        self._narrow_and_renorm(total, vcum, vfreq)
        h.add(symbol)
        return symbol == 0

    def _write_compressed(self, context: int, value: int, raw) -> None:
        self.compressed = True
        if context and context < MAX_RANGE:
            if context > STATIC_FULL:
                escape = self._write_static(context, value + 1)
            else:
                escape = self._write_dynamic(context, value + 1)
            if escape:
                raw(value)
                if context <= STATIC_FULL:
                    self.hist[context].add(value + 1)
        else:
            raw(value)

    # ---- typed writes -------------------------------------------------------
    def write_u8(self, value: int) -> None:
        value &= 0xFF
        if self._initial():
            self._put_bits(value, 8)
        else:
            self._write_static(STATIC_FULL + 256, swap8(value) + 1)

    def write_u16(self, value: int) -> None:
        self.write_u8(value & 0xFF)
        self.write_u8((value >> 8) & 0xFF)

    def write_u32(self, value: int) -> None:
        self.write_u16(value & 0xFFFF)
        self.write_u16((value >> 16) & 0xFFFF)

    def write_u64(self, value: int) -> None:
        self.write_u32(value & 0xFFFFFFFF)
        self.write_u32((value >> 32) & 0xFFFFFFFF)

    def write_f32(self, value: float) -> None:
        self.write_u32(struct.unpack("<I", struct.pack("<f", value))[0])

    def write_f64(self, value: float) -> None:
        self.write_u64(struct.unpack("<Q", struct.pack("<d", value))[0])

    def write_string(self, text: str) -> None:
        raw = text.encode("utf-8")
        self.write_u16(len(raw))
        for b in raw:
            self.write_u8(b)

    def write_cu32(self, context: int, value: int) -> None:
        self._write_compressed(context, value, self.write_u32)

    def write_cu16(self, context: int, value: int) -> None:
        self._write_compressed(context, value, self.write_u16)

    def write_cu8(self, context: int, value: int) -> None:
        self._write_compressed(context, value, self.write_u8)

    def get_bytes(self) -> bytes:
        """Finish like ``GetDataBlockX``: a U32 0 after compressed data, then
        the stream aligned to a byte."""
        if self.compressed:
            self.write_u32(0)
            self.compressed = False
        self.off = (self.off + 7) & ~7
        self._wrap()
        nbytes = self.bitcount() // 8
        nwords = (nbytes + 3) // 4
        self._ensure()
        return struct.pack("<%dI" % nwords, *self.w[:nwords])[:nbytes]


class BitReader(_Coder):
    def __init__(self, data: bytes) -> None:
        super().__init__()
        self.data = bytes(data)
        pad = (-len(self.data)) % 4
        buf = self.data + b"\0" * pad + b"\0" * 64
        self.w = list(struct.unpack_from("<%dI" % (len(buf) // 4), buf))

    # ---- raw bits -----------------------------------------------------------
    def _wrap(self) -> None:
        while self.off >= 32:
            self.off -= 32
            self.pos += 1

    def _seek(self, bits: int) -> None:
        self.pos = bits >> 5
        self.off = bits & 31

    def read_bit(self) -> int:
        v = (self.w[self.pos] >> self.off) & 1
        self.off += 1
        self._wrap()
        return v

    def _read15(self) -> int:
        v = self.w[self.pos] >> self.off
        if self.off > 17:
            v |= self.w[self.pos + 1] << (32 - self.off)
        v = ((v & 0xFFFFFFFF) * 2) & 0xFFFFFFFF
        v = (_SWAP4[(v >> 12) & 0xF] | (_SWAP4[(v >> 8) & 0xF] << 4)
             | (_SWAP4[(v >> 4) & 0xF] << 8) | (_SWAP4[v & 0xF] << 12))
        self.off += 15
        self._wrap()
        return v

    # ---- arithmetic decoder -------------------------------------------------
    def _read_symbol(self, context: int) -> int:
        position = self.bitcount()
        code = self.read_bit()
        self.off += self.underflow
        self._wrap()
        code = (code << 15) | self._read15()
        self._seek(position)
        rng = self.high + 1 - self.low
        if context > STATIC_FULL:
            total = context - STATIC_FULL
            value = (total * (1 + code - self.low) - 1) // rng + 1
            vcum, vfreq, h = value - 1, 1, None
        else:
            h = self._histogram(context)
            total = h.total()
            code_cum = (total * (1 + code - self.low) - 1) // rng
            value = h.symbol_from_freq(code_cum)
            vcum, vfreq = h.cum(value), h.freq(value)
        low = self.low
        high = low - 1 + rng * (vcum + vfreq) // total
        low = low + rng * vcum // total
        if h is not None:
            h.add(value)
        state = ((low << 16) | high) & 0xFFFFFFFF
        bits = 0
        masked = _HALF_MASK & state
        while masked == 0 or masked == _HALF_MASK:
            state = (((_NOT_HALF & state) << 1) | 1) & 0xFFFFFFFF
            masked = _HALF_MASK & state
            bits += 1
        saved = masked
        if bits > 0:
            bits += self.underflow
            self.underflow = 0
        masked = _QUARTER_MASK & state
        extra = 0
        while masked == 0x40000000:
            state &= _NOT_3Q
            state = ((state + state) | 1) & 0xFFFFFFFF
            masked = _QUARTER_MASK & state
            extra += 1
        self.underflow += extra
        state |= saved
        self.low = state >> 16
        self.high = state & 0xFFFF
        self.off += bits
        self._wrap()
        return value

    def _read_compressed(self, context: int, raw) -> int:
        if context and context < MAX_RANGE:
            v = self._read_symbol(context)
            if v != 0:
                return v - 1
            v = raw()
            if context <= STATIC_FULL:
                self._histogram(context).add(v + 1)
            return v
        return raw()

    # ---- typed reads --------------------------------------------------------
    def u8(self) -> int:
        if self._initial():
            v = self.w[self.pos] >> self.off
            if self.off > 24:
                v |= self.w[self.pos + 1] << (32 - self.off)
            v &= 0xFF
            self.off += 8
            self._wrap()
            return v
        return swap8(self._read_symbol(STATIC_FULL + 256) - 1)

    def u16(self) -> int:
        lo = self.u8()
        return lo | (self.u8() << 8)

    def u32(self) -> int:
        lo = self.u16()
        return lo | (self.u16() << 16)

    def u64(self) -> int:
        lo = self.u32()
        return lo | (self.u32() << 32)

    def f32(self) -> float:
        return struct.unpack("<f", struct.pack("<I", self.u32()))[0]

    def f64(self) -> float:
        return struct.unpack("<d", struct.pack("<Q", self.u64()))[0]

    def string(self) -> str:
        n = self.u16()
        return bytes(self.u8() for _ in range(n)).decode("utf-8", "replace")

    def cu32(self, context: int) -> int:
        return self._read_compressed(context, self.u32)

    def cu16(self, context: int) -> int:
        return self._read_compressed(context, self.u16)

    def cu8(self, context: int) -> int:
        return self._read_compressed(context, self.u8)

    def rest(self) -> bytes:
        """The bytes after the current (byte-aligned) position: a texture
        continuation's image data."""
        return self.data[(self.bitcount() + 7) // 8:]
