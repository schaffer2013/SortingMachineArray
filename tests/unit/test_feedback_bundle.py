import json
from pathlib import Path
import zipfile

from sorter.application.feedback_bundle import build_submodule_feedback_bundle


def test_build_submodule_feedback_bundle_packages_existing_docs_and_reports(tmp_path: Path):
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "submodule_feedback.md").write_text("# feedback\n", encoding="utf-8")
    (tmp_path / "docs" / "acceptance_gates.md").write_text("# gates\n", encoding="utf-8")
    portable_dir = tmp_path / "data" / "recognition_reports" / "portable"
    portable_dir.mkdir(parents=True)
    (tmp_path / "data" / "recognition_reports" / "acceptance_envelope.json").write_text("{}", encoding="utf-8")
    (portable_dir / "demo.portable.json").write_text("{}", encoding="utf-8")

    output_path = tmp_path / "bundle.zip"
    manifest = build_submodule_feedback_bundle(tmp_path, output_path)

    assert output_path.exists()
    assert len(manifest.entries) == 4
    with zipfile.ZipFile(output_path) as bundle:
        names = set(bundle.namelist())
        assert "manifest.json" in names
        assert "docs/submodule_feedback.md" in names
        assert "docs/acceptance_gates.md" in names
        assert "data/recognition_reports/acceptance_envelope.json" in names
        assert "data/recognition_reports/portable/demo.portable.json" in names
        payload = json.loads(bundle.read("manifest.json").decode("utf-8"))
        assert payload["entries"][0]["archive_path"] == "docs/submodule_feedback.md"
