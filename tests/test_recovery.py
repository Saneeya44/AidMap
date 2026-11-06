
import io
import unittest
import struct
import zlib

from src.format import (
    CorruptFrameError,
    encode_header,
    encode_transaction,
)
from src.recovery import recover


class TestRecovery(unittest.TestCase):

    def test_empty_database(self):
        # Create a database containing only its header.
        fh = io.BytesIO(encode_header())

        # Recovery starts immediately after the header.
        fh.seek(5)

        # Run our recovery function.
        index, valid_end = recover(fh)

        # There should be no keys in an empty database.
        self.assertEqual(index, {})

        # The last valid position should be byte 5.
        self.assertEqual(valid_end, 5)

    def test_multiple_transactions(self):
        # Transaction 1: save a name.
        first = encode_transaction([
            ("put", b"name", b"Alex")
        ])

        # Transaction 2: save an age.
        second = encode_transaction([
            ("put", b"age", b"20")
        ])

        # Construct a database file in memory.
        database_bytes = encode_header() + first + second
        fh = io.BytesIO(database_bytes)

        # Skip the five-byte database header.
        fh.seek(5)

        # Recover both transactions.
        index, valid_end = recover(fh)

        # Verify both values were restored.
        self.assertEqual(index[b"name"], b"Alex")
        self.assertEqual(index[b"age"], b"20")

        # Verify the absolute end offset.
        self.assertEqual(
            valid_end,
            5 + len(first) + len(second)
        )
    
    def test_ordered_batch(self):
        # All four operations belong to ONE transaction.
        batch_frame = encode_transaction([
            ("put", b"name", b"Alex"),
            ("put", b"score", b"90"),
            ("put", b"score", b"100"),
            ("delete", b"name", None),
        ])

        # Build an in-memory database file.
        database_bytes = encode_header() + batch_frame
        fh = io.BytesIO(database_bytes)

        # Skip the 5-byte database header.
        fh.seek(5)

        # Recover the transaction.
        index, valid_end = recover(fh)

        # The last PUT for score should win.
        self.assertEqual(index[b"score"], b"100")

        # The DELETE should mark name as deleted.
        self.assertIn(b"name", index)
        self.assertIsNone(index[b"name"])

        # The entire batch must be recovered.
        self.assertEqual(
            valid_end,
            5 + len(batch_frame)
        )
    
    def test_truncated_final_transaction(self):
        # A fully committed transaction.
        good_frame = encode_transaction([
            ("put", b"safe", b"yes")
        ])

        # A transaction that will be interrupted.
        next_frame = encode_transaction([
            ("put", b"unsafe", b"no")
        ])

        # Simulate a crash at every possible byte
        # before the second frame is complete.
        for cut in range(1, len(next_frame)):
            with self.subTest(cut=cut):
                database_bytes = (
                    encode_header()
                    + good_frame
                    + next_frame[:cut]
                )

                fh = io.BytesIO(database_bytes)
                fh.seek(5)

                index, valid_end = recover(fh)

                # The committed transaction survives.
                self.assertEqual(
                    index[b"safe"], b"yes"
                )

                # The incomplete transaction is ignored.
                self.assertNotIn(b"unsafe", index)

                # The safe offset stays after good_frame.
                self.assertEqual(
                    valid_end,
                    5 + len(good_frame)
                )
    
    def test_invalid_crc(self):
        # Create a valid transaction.
        frame = bytearray(encode_transaction([
            ("put", b"key", b"value")
        ]))

        # Corrupt one byte of the CRC32 checksum.
        # The checksum occupies the 4 bytes before CMIT.
        frame[-8] ^= 0xFF

        database_bytes = encode_header() + bytes(frame)
        fh = io.BytesIO(database_bytes)
        fh.seek(5)

        # A complete frame with a bad CRC must raise.
        with self.assertRaises(CorruptFrameError):
            recover(fh)

    def test_invalid_commit_marker(self):
        # Create a valid transaction.
        frame = bytearray(encode_transaction([
            ("put", b"key", b"value")
        ]))

        # Corrupt the final byte of the CMIT marker.
        frame[-1] ^= 0xFF

        database_bytes = encode_header() + bytes(frame)
        fh = io.BytesIO(database_bytes)
        fh.seek(5)

        # A complete frame with a bad marker must raise.
        with self.assertRaises(CorruptFrameError):
            recover(fh)
    
    def test_invalid_payload_structure(self):
        frame = bytearray(encode_transaction([
            ("put", b"key", b"value")
        ]))

        payload_length = struct.unpack("<I", frame[:4])[0]
        payload = bytearray(frame[4:4 + payload_length])

        # Replace the operation type with invalid type 99.
        payload[4] = 99

        # Recompute CRC so only structural validation
        # can detect the invalid operation.
        frame[4:4 + payload_length] = payload

        crc_offset = 4 + payload_length
        frame[crc_offset:crc_offset + 4] = struct.pack(
            "<I", zlib.crc32(payload) & 0xFFFFFFFF
        )

        fh = io.BytesIO(encode_header() + bytes(frame))
        fh.seek(5)

        with self.assertRaises(CorruptFrameError):
            recover(fh)

    def test_invalid_frame_length(self):
        # A transaction payload must contain at least
        # the 4-byte operation count.
        invalid_length = struct.pack("<I", 3)

        fh = io.BytesIO(encode_header() + invalid_length)
        fh.seek(5)

        # A payload shorter than 4 bytes is invalid.
        with self.assertRaises(CorruptFrameError):
            recover(fh)

if __name__ == "__main__":
    unittest.main()
