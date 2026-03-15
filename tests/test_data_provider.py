from quodeq.bootstrap import DataProvider
from quodeq.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository


def test_data_provider_exposes_evaluators_repo(tmp_path):
    repo = FilesystemEvaluatorsRepository(root=tmp_path)
    provider = DataProvider(evaluators=repo)
    assert provider.evaluators is repo
