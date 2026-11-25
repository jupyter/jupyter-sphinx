from types import SimpleNamespace

from jupyter_sphinx.utils import output_directory


def test_output_directories_do_not_share_artifacts(tmp_path):
    outputs = []
    for name in ("first", "second"):
        env = SimpleNamespace(
            app=SimpleNamespace(outdir=tmp_path / name),
            doctreedir=tmp_path / f"{name}-doctrees",
        )
        output = output_directory(env)
        output.mkdir(parents=True, exist_ok=True)
        script = output / "index.py"
        script.write_text(name, encoding="utf8")
        outputs.append(script)

    assert [script.read_text(encoding="utf8") for script in outputs] == ["first", "second"]


def test_output_directory_is_shared_within_doctree_cache(tmp_path):
    env = SimpleNamespace(
        app=SimpleNamespace(outdir=tmp_path / "html"),
        doctreedir=tmp_path / "doctrees",
    )
    output = output_directory(env)
    output.mkdir(parents=True)
    script = output / "index.py"
    script.write_text("cached", encoding="utf8")

    env.app.outdir = tmp_path / "latex"
    assert (output_directory(env) / "index.py").read_text(encoding="utf8") == "cached"
