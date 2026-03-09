from quodeq.config.sources import has_required_sources_table


def test_sources_table_detection():
    content = """| Sources | Tier | URL | Notes |\n| --- | --- | --- | --- |\n| A | T1 | http://x | - |\n"""
    assert has_required_sources_table(content)
