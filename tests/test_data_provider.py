from codecompass.bootstrap import DataProvider
from codecompass.adapters.fs.practices_repository import FilesystemPracticesRepository


def test_data_provider_exposes_practices_repo(tmp_path):
    provider = DataProvider(practices=FilesystemPracticesRepository(root=tmp_path))
    assert provider.practices is not None
