from codecompass.config.practices_manager import generate_practice_file
from codecompass.config.practices_manager import generate_practices_for_discipline
from codecompass.config.practices_manager import list_practice_names


def test_list_practice_names(tmp_path):
    (tmp_path / "one.json").write_text("{}")
    (tmp_path / "two.json").write_text("{}")
    names = list_practice_names(tmp_path)
    assert names == ["one", "two"]


def test_generate_practice_file_writes_json(tmp_path, monkeypatch):
    discipline_dir = tmp_path / "backend"
    discipline_dir.mkdir()

    def fake_run_ai(prompt: str):
        return "{\"metadata\": {\"topic\": \"SOLID\"}, \"practices_index\": [], \"body\": \"\"}\n", None

    monkeypatch.setattr("codecompass.config.generators.run_ai_cli", fake_run_ai)

    template_path = tmp_path / "principles-generator.md"
    template_path.write_text("Disc={{DISCIPLINE}}")

    output = generate_practice_file(
        discipline="backend",
        topic="SOLID",
        language="Python",
        output_dir=discipline_dir,
        template_path=template_path,
    )
    assert output.exists()
    assert output.suffix == ".json"


def test_generate_practices_for_discipline_runs_all(tmp_path, monkeypatch):
    discipline_dir = tmp_path / "backend"
    discipline_dir.mkdir()

    generated = []

    def fake_generate(**kwargs):
        path = discipline_dir / f"{kwargs['topic'].lower()}.json"
        path.write_text("{}")
        generated.append(path)
        return path

    monkeypatch.setattr(
        "codecompass.config.practices_manager.generate_practice_file",
        fake_generate,
    )

    topics = ["SOLID", "Error Handling"]
    generate_practices_for_discipline(
        discipline="backend",
        language="Python",
        topics=topics,
        output_dir=discipline_dir,
        template_path=tmp_path / "principles-generator.md",
    )
    assert len(generated) == 2
