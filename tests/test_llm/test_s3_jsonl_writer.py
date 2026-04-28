"""Tests for S3JsonlWriter — streaming JSONL upload to S3."""

import json
from unittest.mock import MagicMock

import pytest

from app.llm.queue.s3_jsonl_writer import S3JsonlWriter, iter_s3_jsonl


@pytest.fixture
def mock_s3():
    s3 = MagicMock()
    s3.create_multipart_upload.return_value = {"UploadId": "upload-id-1"}
    s3.upload_part.side_effect = lambda **kw: {"ETag": f"etag-{kw['PartNumber']}"}
    return s3


class TestS3JsonlWriterSinglePut:
    """Small payloads should use a single PutObject, not multipart."""

    def test_writes_single_record_via_put_object(self, mock_s3):
        with S3JsonlWriter(mock_s3, "bucket", "key.jsonl") as w:
            w.write_record({"a": 1})

        mock_s3.create_multipart_upload.assert_not_called()
        mock_s3.upload_part.assert_not_called()
        mock_s3.complete_multipart_upload.assert_not_called()
        mock_s3.put_object.assert_called_once()
        kwargs = mock_s3.put_object.call_args.kwargs
        assert kwargs["Bucket"] == "bucket"
        assert kwargs["Key"] == "key.jsonl"
        assert kwargs["Body"] == b'{"a": 1}\n'
        assert kwargs["ContentType"] == "application/jsonl"

    def test_writes_many_small_records_via_put_object(self, mock_s3):
        with S3JsonlWriter(mock_s3, "bucket", "key.jsonl") as w:
            for i in range(50):
                w.write_record({"i": i})

        # Total payload tiny — single PutObject
        mock_s3.create_multipart_upload.assert_not_called()
        mock_s3.put_object.assert_called_once()
        body = mock_s3.put_object.call_args.kwargs["Body"].decode("utf-8")
        lines = [line for line in body.split("\n") if line]
        assert len(lines) == 50
        assert json.loads(lines[0]) == {"i": 0}
        assert json.loads(lines[49]) == {"i": 49}


class TestS3JsonlWriterMultipart:
    """Payloads exceeding part_size should switch to multipart upload."""

    def test_switches_to_multipart_above_part_size(self, mock_s3):
        # Each ~150-byte record exceeds the 100B threshold, so every write
        # triggers a flush — 5 records → 5 parts, no residual.
        with S3JsonlWriter(mock_s3, "bucket", "key.jsonl", part_size=100) as w:
            for i in range(5):
                w.write_record({"i": i, "padding": "x" * 140})

        mock_s3.create_multipart_upload.assert_called_once()
        assert mock_s3.upload_part.call_count == 5
        mock_s3.complete_multipart_upload.assert_called_once()
        kwargs = mock_s3.complete_multipart_upload.call_args.kwargs
        assert kwargs["UploadId"] == "upload-id-1"
        assert len(kwargs["MultipartUpload"]["Parts"]) == 5
        assert mock_s3.put_object.call_count == 0

    def test_residual_buffer_flushed_as_final_part(self, mock_s3):
        # part_size=200 bytes; first record fits, second exceeds
        with S3JsonlWriter(mock_s3, "bucket", "key.jsonl", part_size=200) as w:
            w.write_record({"a": "x" * 50})  # ~60B, buffered
            w.write_record({"b": "y" * 200})  # pushes over → flush part 1
            w.write_record({"c": "z" * 50})  # buffered, flushed by close()

        mock_s3.create_multipart_upload.assert_called_once()
        # 1 mid-stream flush + 1 final residual flush in close()
        assert mock_s3.upload_part.call_count == 2
        mock_s3.complete_multipart_upload.assert_called_once()

    def test_record_count_accurate_across_multipart_boundary(self, mock_s3):
        # record_count is the value callers (e.g. SFN ResultSelector) read.
        # Assert it directly rather than implying it via captured Body length.
        w = S3JsonlWriter(mock_s3, "bucket", "key.jsonl", part_size=100)
        for i in range(7):
            w.write_record({"i": i, "padding": "x" * 140})
        assert w.record_count == 7
        w.close()
        # Count is unchanged after close (close doesn't write more records).
        assert w.record_count == 7
        # And the multipart path was actually exercised — confirms we tested
        # the boundary, not a small-payload fast path.
        mock_s3.create_multipart_upload.assert_called_once()


class TestS3JsonlWriterAbort:
    """Exceptions inside the with block should abort the upload cleanly."""

    def test_aborts_multipart_on_exception(self, mock_s3):
        with pytest.raises(RuntimeError, match="boom"):
            with S3JsonlWriter(mock_s3, "bucket", "key.jsonl", part_size=100) as w:
                w.write_record({"big": "x" * 200})  # triggers multipart start
                raise RuntimeError("boom")

        mock_s3.create_multipart_upload.assert_called_once()
        mock_s3.abort_multipart_upload.assert_called_once()
        mock_s3.complete_multipart_upload.assert_not_called()

    def test_abort_is_noop_if_no_multipart_started(self, mock_s3):
        with pytest.raises(RuntimeError, match="early"):
            with S3JsonlWriter(mock_s3, "bucket", "key.jsonl"):
                raise RuntimeError("early")

        mock_s3.create_multipart_upload.assert_not_called()
        mock_s3.abort_multipart_upload.assert_not_called()
        mock_s3.put_object.assert_not_called()


class TestIterS3Jsonl:
    """Reading JSONL back from S3 line by line."""

    def test_iterates_records(self):
        s3 = MagicMock()
        body = MagicMock()
        body.iter_lines.return_value = iter([b'{"id": 1}', b'{"id": 2}', b'{"id": 3}'])
        s3.get_object.return_value = {"Body": body}

        records = list(iter_s3_jsonl(s3, "bucket", "key"))

        assert records == [{"id": 1}, {"id": 2}, {"id": 3}]
        s3.get_object.assert_called_once_with(Bucket="bucket", Key="key")

    def test_skips_blank_lines(self):
        s3 = MagicMock()
        body = MagicMock()
        body.iter_lines.return_value = iter([b'{"id": 1}', b"", b'{"id": 2}'])
        s3.get_object.return_value = {"Body": body}

        records = list(iter_s3_jsonl(s3, "bucket", "key"))

        assert records == [{"id": 1}, {"id": 2}]
