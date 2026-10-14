# SPDX-License-Identifier: GPL-3.0-or-later
import random
import struct

import pytest

from igz_pdf3d._u3d_bits import BitReader, BitWriter, Histogram, MAX_RANGE, STATIC_FULL


def test_plain_values_are_little_endian_bytes():
    w = BitWriter()
    w.write_u32(0x00443355)
    w.write_u16(0x1234)
    w.write_u8(0xAB)
    w.write_f32(1.5)
    w.write_string("Box01")
    out = w.get_bytes()
    assert out == struct.pack("<IHBf", 0x00443355, 0x1234, 0xAB, 1.5) + b"\x05\x00Box01"
    r = BitReader(out)
    assert r.u32() == 0x00443355
    assert r.u16() == 0x1234
    assert r.u8() == 0xAB
    assert r.f32() == 1.5
    assert r.string() == "Box01"


def test_u64_and_f64_round_trip():
    w = BitWriter()
    w.write_u64(0x0102030405060708)
    w.write_f64(-2.25)
    r = BitReader(w.get_bytes())
    assert r.u64() == 0x0102030405060708
    assert r.f64() == -2.25


def test_reads_sample_file_header(data_dir):
    data = (data_dir / "box.u3d").read_bytes()
    btype, size, meta = struct.unpack_from("<III", data, 0)
    assert btype == 0x00443355 and size == 24 and meta == 0
    r = BitReader(data[12:12 + size])
    assert r.u32() == 0            # version
    assert r.u32() == 0            # profile
    assert r.u32() == 36           # declaration size as the reference writes it
    assert r.u64() == 1276         # file size
    assert r.u32() == 106          # UTF-8


def test_static_context_round_trip():
    rnd = random.Random(1)
    values = [rnd.randrange(8) for _ in range(2000)]
    w = BitWriter()
    for v in values:
        w.write_cu32(STATIC_FULL + 8, v)
    out = w.get_bytes()
    assert len(out) < 2000            # compressed: 3 bits per symbol at most
    r = BitReader(out)
    assert [r.cu32(STATIC_FULL + 8) for _ in values] == values
    assert r.u32() == 0               # the trailing marker the writer appends


def test_dynamic_context_round_trip_with_growth_and_rescale():
    rnd = random.Random(2)
    values = [rnd.choice([0, 1, 2, 3, 250, 1000]) for _ in range(20000)]
    w = BitWriter()
    for v in values:
        w.write_cu32(1, v)
    r = BitReader(w.get_bytes())
    assert [r.cu32(1) for _ in values] == values


def test_cu16_and_cu8_round_trip():
    w = BitWriter()
    for v in (0, 1, 1, 65535, 7, 7, 7):
        w.write_cu16(99, v)
    for v in (0, 2, 2, 255, 1):
        w.write_cu8(2, v)
    r = BitReader(w.get_bytes())
    assert [r.cu16(99) for _ in range(7)] == [0, 1, 1, 65535, 7, 7, 7]
    assert [r.cu8(2) for _ in range(5)] == [0, 2, 2, 255, 1]


def test_plain_values_after_compressed_use_static_byte_context():
    w = BitWriter()
    w.write_string("Mesh")
    w.write_cu32(1, 5)
    w.write_u32(0xDEADBEEF)
    w.write_f32(-3.0)
    w.write_string("after")
    w.write_cu32(STATIC_FULL + 3, 2)
    r = BitReader(w.get_bytes())
    assert r.string() == "Mesh"
    assert r.cu32(1) == 5
    assert r.u32() == 0xDEADBEEF
    assert r.f32() == -3.0
    assert r.string() == "after"
    assert r.cu32(STATIC_FULL + 3) == 2


def test_cu32_beyond_static_range_round_trips():
    n = 20000                         # more positions than the static contexts allow
    assert STATIC_FULL + n >= MAX_RANGE
    w = BitWriter()
    w.write_cu32(STATIC_FULL + 5, 4)  # put the coder in a non-initial state first
    for v in (0, 19999, 12345):
        w.write_cu32(STATIC_FULL + n, v)
    r = BitReader(w.get_bytes())
    assert r.cu32(STATIC_FULL + 5) == 4
    assert [r.cu32(STATIC_FULL + n) for _ in range(3)] == [0, 19999, 12345]


def test_context_zero_is_plain():
    w = BitWriter()
    w.write_cu32(0, 77)
    r = BitReader(w.get_bytes())
    assert r.cu32(0) == 77


def test_writer_is_deterministic():
    def make():
        w = BitWriter()
        for i in range(300):
            w.write_cu32(1, i % 7)
            w.write_cu32(STATIC_FULL + 300, i)
        return w.get_bytes()
    assert make() == make()


def test_histogram_matches_reference_semantics():
    h = Histogram()
    assert h.total() == 1 and h.freq(0) == 1 and h.cum(0) == 0
    h.add(3)
    assert h.total() == 2 and h.freq(3) == 1 and h.cum(3) == 1 and h.cum(4) == 2
    assert h.symbol_from_freq(0) == 0 and h.symbol_from_freq(1) == 3
    h.add(500)                        # growth beyond the initial 100 symbols
    assert h.freq(500) == 1 and h.total() == 3
    for _ in range(0x1FFF):
        h.add(2)                      # forces the elephant rescale
    assert h.total() < 0x1FFF + 3
    assert h.freq(0) >= 1


def test_bitcount_and_rest():
    w = BitWriter()
    w.write_string("T")
    w.write_u32(0)
    r = BitReader(w.get_bytes() + b"\xff\xd8\xff")
    r.string()
    r.u32()
    assert r.bitcount() == 7 * 8
    assert r.rest() == b"\xff\xd8\xff"
