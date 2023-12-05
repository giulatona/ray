import os
from typing import Any, Dict

import pyarrow
import pytest

import ray
from ray.data.block import BlockAccessor
from ray.data.datasource import BlockBasedFileDatasink, RowBasedFileDatasink


class MockFileDatasink(BlockBasedFileDatasink):
    def write_block_to_file(self, block: BlockAccessor, file: "pyarrow.NativeFile"):
        file.write(b"")


def test_flaky_block_write(ray_start_regular_shared, tmp_path):
    class FlakyCSVDatasink(BlockBasedFileDatasink):
        def __init__(self, path: str):
            super().__init__(path)
            self._num_attempts = 0

        def write_block_to_file(self, block: BlockAccessor, file: "pyarrow.NativeFile"):
            if self._num_attempts < 2:
                self._num_attempts += 1
                raise RuntimeError("AWS Error INTERNAL_FAILURE")

            block.to_pandas().to_csv(file)

    ds = ray.data.range(100)

    ds.write_datasink(FlakyCSVDatasink(tmp_path))

    expected_values = list(range(100))
    written_values = [row["id"] for row in ray.data.read_csv(tmp_path).take_all()]
    assert sorted(written_values) == sorted(expected_values)


def test_flaky_row_write(ray_start_regular_shared, tmp_path):
    class FlakyTextDatasink(RowBasedFileDatasink):
        def __init__(self, path: str):
            super().__init__(path)
            self._num_attempts = 0

        def write_row_to_file(self, row: Dict[str, Any], file: "pyarrow.NativeFile"):
            if self._num_attempts < 2:
                self._num_attempts += 1
                raise RuntimeError("AWS Error INTERNAL_FAILURE")

            file.write(f"{row['id']}".encode())

    ds = ray.data.range(100)

    ds.write_datasink(FlakyTextDatasink(tmp_path))

    expected_values = [str(i) for i in range(100)]
    written_values = [row["text"] for row in ray.data.read_text(tmp_path).take_all()]
    assert sorted(written_values) == sorted(expected_values)


@pytest.mark.parametrize("num_rows", [0, 1])
def test_write_preserves_user_directory(num_rows, tmp_path, ray_start_regular_shared):
    ds = ray.data.range(num_rows)
    path = os.path.join(tmp_path, "test")
    os.mkdir(path)  # User-created directory

    ds.write_datasource(MockFileDatasink(path=path))

    assert os.path.isdir(path)


def test_write_creates_dir(tmp_path, ray_start_regular_shared):
    ds = ray.data.range(1)
    path = os.path.join(tmp_path, "test")

    ds.write_datasource(MockFileDatasink(path=path, try_create_dir=True))

    assert os.path.isdir(path)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(["-v", __file__]))