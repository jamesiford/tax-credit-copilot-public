"""The Cowork plugin package: it builds, it is reproducible, and it validates. [CH-10]

Three things must stay true. The package builds offline from placeholder values and the
same inputs give the same bytes. The validator refuses each class of mistake the Cowork
documentation warns about, and each refusal is shown here firing on a crafted package, so a
validator nobody has seen fail is not trusted. And the skills teach only tools the gateway
actually serves: a skill that names a renamed or unbuilt tool fails here, not in front of a user.
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from application.capabilities import catalog  # noqa: E402
from channel.mcp import describe  # noqa: E402
from cowork_plugin import frontmatter, icons, package  # noqa: E402
from cowork_plugin.findings import errors  # noqa: E402
from cowork_plugin.manifest import TOOL_FILE, render_manifest  # noqa: E402
from cowork_plugin.settings import ConfigError, app_id_for, load_settings  # noqa: E402
from cowork_plugin.validate_content import tool_references, validate_neutrality, validate_tools  # noqa: E402
from cowork_plugin.validate_manifest import validate_manifest  # noqa: E402
from cowork_plugin.validate_skills import validate_skills  # noqa: E402

PLUGIN = REPO / "channels" / "cowork"
PLACEHOLDERS = {
    "developer_name": "Example Developer", "developer_website_url": "https://developer.example.com",
    "developer_privacy_url": "https://developer.example.com/privacy", "developer_terms_url": "https://developer.example.com/terms",
    "gateway_mcp_url": "https://gateway.example.com/mcp", "oauth_reference_id": "00000000-0000-0000-0000-000000000000",
}
SKILLS = ("tcc-book-review", "tcc-client-review-pack", "tcc-figures-and-writes")


def settings(tmp_path: Path, **overrides: str):
    path = tmp_path / "cowork.json"
    path.write_text(json.dumps({**PLACEHOLDERS, **overrides}), encoding="utf-8")
    return load_settings(path, environ={})


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """The real sources, assembled with placeholder values."""
    tmp = tmp_path_factory.mktemp("cowork")
    configured = settings(tmp)
    document, files = package.assemble(configured)
    return configured, document, files


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def skill(name: str, body: str = "Body.", description: str = "Use when asked.", folder: str | None = None) -> dict[str, bytes]:
    return {f"skills/{folder or name}/SKILL.md": f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n".encode()}


def manifest_for(*folders: str) -> dict:
    return {"agentSkills": [{"folder": f"./skills/{f}"} for f in folders]}


# ----------------------------------------------------------------------- the build


def test_the_package_builds_from_placeholder_values_and_holds_exactly_what_it_should(tmp_path):
    result = package.build(settings(tmp_path), tmp_path / "out")
    with zipfile.ZipFile(result.zip_path) as archive:
        names = set(archive.namelist())
    skill_files = {n for n in names if n.startswith("skills/")}
    assert names - skill_files == {"manifest.json", "color.png", "outline.png"}
    assert {n.split("/")[1] for n in skill_files} == set(SKILLS)
    assert all(f"skills/{s}/SKILL.md" in names for s in SKILLS)
    assert not any(n.startswith("tools/") for n in names), "manifest 1.29 connectors are URL-only"
    assert not errors(result.findings)


def test_two_builds_of_the_same_inputs_hash_the_same(tmp_path):
    first = package.build(settings(tmp_path), tmp_path / "a")
    second = package.build(settings(tmp_path), tmp_path / "b")
    assert first.sha256 == second.sha256 and first.zip_path.read_bytes() == second.zip_path.read_bytes()


def test_a_changed_input_changes_the_hash(tmp_path):
    base = package.build(settings(tmp_path), tmp_path / "a").sha256
    assert package.build(settings(tmp_path, version="1.0.1"), tmp_path / "b").sha256 != base
    assert package.build(settings(tmp_path, gateway_mcp_url="https://gateway.example.org/mcp"), tmp_path / "c").sha256 != base


def test_line_endings_do_not_change_the_hash(tmp_path):
    crlf = tmp_path / "cowork"
    for source in PLUGIN.rglob("*"):
        target = crlf / source.relative_to(PLUGIN)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.suffix in (".md", ".json"):
            target.write_bytes(source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        else:
            target.write_bytes(source.read_bytes())
    plain = package.build(settings(tmp_path), tmp_path / "a")
    windows = package.build(settings(tmp_path), tmp_path / "b", root=crlf)
    assert plain.sha256 == windows.sha256


def test_every_timestamp_in_the_zip_is_fixed(tmp_path):
    result = package.build(settings(tmp_path), tmp_path / "out")
    with zipfile.ZipFile(result.zip_path) as archive:
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_the_app_id_is_deterministic_and_changes_with_the_seed(tmp_path):
    assert settings(tmp_path).app_id == app_id_for("tcc-channel.cowork-plugin")
    assert settings(tmp_path, app_id_seed="another").app_id != settings(tmp_path).app_id
    assert settings(tmp_path, app_id="11111111-2222-3333-4444-555555555555").app_id.startswith("11111111")


def test_an_environment_value_overrides_the_file(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(PLACEHOLDERS), encoding="utf-8")
    loaded = load_settings(path, environ={"TCC_COWORK_GATEWAY_MCP_URL": "https://gateway.example.net/mcp"})
    assert loaded.values["gateway_mcp_url"] == "https://gateway.example.net/mcp"


def test_missing_configuration_is_named_not_guessed(tmp_path):
    with pytest.raises(ConfigError, match="gateway_mcp_url"):
        load_settings(None, environ={})
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({**PLACEHOLDERS, "manifest_version": "1.30"}), encoding="utf-8")
    with pytest.raises(ConfigError, match="manifest_version"):
        load_settings(bad, environ={})


def test_placeholders_build_but_strict_refuses_them(tmp_path):
    configured = settings(tmp_path)
    assert set(configured.placeholders()) == {"developer_website_url", "developer_privacy_url", "developer_terms_url", "gateway_mcp_url", "oauth_reference_id"}
    with pytest.raises(package.BuildError, match="placeholder"):
        package.build(configured, tmp_path / "out", strict=True)
    real_values = settings(
        tmp_path, developer_website_url="https://dev.invalid-tld.test", developer_privacy_url="https://dev.invalid-tld.test/p",
        developer_terms_url="https://dev.invalid-tld.test/t", gateway_mcp_url="https://gw.invalid-tld.test/mcp",
        oauth_reference_id="abc123refid",
    )
    assert not real_values.placeholders()
    assert package.build(real_values, tmp_path / "ok", strict=True).zip_path.is_file()


# -------------------------------------------------------------------- the manifest


def test_the_manifest_is_1_29_with_one_url_only_oauth_connector(real):
    _, manifest, _ = real
    assert manifest["manifestVersion"] == "1.29" and "/v1.29/" in manifest["$schema"]
    assert [c["id"] for c in manifest["agentConnectors"]] == ["tcc-channel"]
    server = manifest["agentConnectors"][0]["toolSource"]["remoteMcpServer"]
    assert server["mcpServerUrl"].startswith("https://") and server["mcpServerUrl"].endswith("/mcp")
    assert "mcpToolDescription" not in server
    assert server["authorization"] == {"type": "OAuthPluginVault", "referenceId": PLACEHOLDERS["oauth_reference_id"]}
    assert "packageName" not in manifest


def test_every_skill_folder_is_registered_and_present(real):
    _, manifest, files = real
    folders = [entry["folder"] for entry in manifest["agentSkills"]]
    assert sorted(f.rsplit("/", 1)[-1] for f in folders) == sorted(SKILLS)
    assert all(f"{f.removeprefix('./')}/SKILL.md" in files for f in folders)


def test_manifest_1_28_carries_a_tool_file_generated_from_the_catalog(tmp_path):
    result = package.build(settings(tmp_path, manifest_version="1.28"), tmp_path / "out")
    tools = json.loads(result.files[TOOL_FILE])["tools"]
    assert [t["name"] for t in tools] == [s.name for s in catalog.offered()]
    assert tools == [describe(s) for s in catalog.offered()], "the file is the gateway's own tools/list, not a hand-written list"
    manifest = json.loads(result.files["manifest.json"])
    assert manifest["agentConnectors"][0]["toolSource"]["remoteMcpServer"]["mcpToolDescription"] == {"file": "./" + TOOL_FILE}


def test_the_manifest_validates_against_the_published_schema_when_it_is_available(real):
    """A dev-time cross-check: the schema is not vendored, so this runs only where it was fetched."""
    schema = Path(__import__("os").environ.get("TEMP", "/tmp")) / "schema129.json"
    if not schema.is_file():
        assert not errors(validate_manifest(real[1], real[2])), "the offline rules are the gate when the schema is absent"
        return
    import jsonschema

    assert list(jsonschema.Draft7Validator(json.loads(schema.read_text(encoding="utf-8"))).iter_errors(real[1])) == []


def test_the_icons_are_the_right_size_and_deterministic():
    assert icons.png_size(icons.color_icon("#0F6CBD")) == (192, 192) and icons.png_size(icons.outline_icon()) == (32, 32)
    assert icons.color_icon("#0F6CBD") == icons.color_icon("#0F6CBD") and icons.outline_icon() == icons.outline_icon()
    assert icons.color_icon("#0F6CBD") != icons.color_icon("#B91C1C")
    with pytest.raises(ValueError):
        icons.png_size(b"GIF89a-not-a-png-at-all-xxxxxxxxxxxxxxxx")


# ---------------------------------------------------------------- the validator bites


@pytest.mark.parametrize(("mutate", "code"), [
    (lambda m: m.update(packageName="x"), "TCC-M001"),
    (lambda m: m.pop("id"), "TCC-M001"),
    (lambda m: m.update(id="not-a-guid"), "TCC-M004"),
    (lambda m: m.update(version="1.0"), "TCC-M004"),
    (lambda m: m.update(accentColor="blue"), "TCC-M004"),
    (lambda m: m["developer"].update(privacyUrl="http://insecure.example.com"), "TCC-M005"),
    (lambda m: m["name"].update(short="x" * 31), "TCC-M002"),
    (lambda m: m["description"].update(short="x" * 81), "TCC-M002"),
    (lambda m: m["icons"].update(color="missing.png"), "TCC-M006"),
    (lambda m: m["agentConnectors"][0]["toolSource"]["remoteMcpServer"].update(mcpServerUrl="http://gateway.example.com/mcp"), "TCC-C003"),
    (lambda m: m["agentConnectors"][0]["toolSource"]["remoteMcpServer"]["authorization"].pop("referenceId"), "TCC-C005"),
    (lambda m: m["agentConnectors"][0]["toolSource"]["remoteMcpServer"].update(authorization={"type": "None", "referenceId": "x"}), "TCC-C005"),
    (lambda m: m["agentConnectors"][0]["toolSource"]["remoteMcpServer"].update(mcpToolDescription={"file": "./tools/x.json"}), "TCC-C004"),
    (lambda m: m["agentConnectors"].append(dict(m["agentConnectors"][0])), "TCC-C001"),
    (lambda m: m["agentConnectors"][0].update(toolSource={"plugin": {}}), "TCC-C002"),
    (lambda m: m["agentSkills"].append({}), "ASKILL-M001"),
    (lambda m: m["agentSkills"].append({"folder": "./skills/" + "x" * 260}), "ASKILL-M003"),
    (lambda m: m.update(agentSkills=[{"folder": f"./skills/s{i}"} for i in range(21)]), "ASKILL-M002"),
])
def test_the_manifest_validator_refuses(real, mutate, code):
    _, manifest, files = real
    broken = json.loads(json.dumps(manifest))
    mutate(broken)
    assert code in codes(validate_manifest(broken, files))


def test_manifest_1_28_without_a_tool_file_is_refused(real):
    _, manifest, files = real
    broken = json.loads(json.dumps(manifest))
    broken["manifestVersion"] = "1.28"
    assert "TCC-C004" in codes(validate_manifest(broken, files))


def test_a_skill_whose_folder_is_not_its_name_is_refused():
    findings = validate_skills(manifest_for("renamed"), skill("tcc-book-review", folder="renamed"))
    assert "ASKILL-P006" in codes(findings)


def test_an_overlong_description_is_refused_and_the_limit_is_inclusive():
    assert "ASKILL-P005" in codes(validate_skills(manifest_for("a-skill"), skill("a-skill", description="x" * 1025)))
    assert not errors(validate_skills(manifest_for("a-skill"), skill("a-skill", description="x" * 1024)))


@pytest.mark.parametrize("name", ["MySkill", "my_skill", "-lead", "trail-", "double--hyphen"])
def test_a_name_that_is_not_kebab_case_is_refused(name):
    assert "ASKILL-P007" in codes(validate_skills(manifest_for(name), skill(name)))


def test_missing_and_malformed_skill_files_are_each_named():
    assert "ASKILL-P001" in codes(validate_skills(manifest_for("absent"), {}))
    assert "ASKILL-P002" in codes(validate_skills(manifest_for("a-skill"), {"skills/a-skill/notes.md": b"x"}))
    assert "ASKILL-P003" in codes(validate_skills(manifest_for("a-skill"), {"skills/a-skill/SKILL.md": b"no frontmatter"}))
    assert "ASKILL-P003" in codes(validate_skills(manifest_for("a-skill"), {"skills/a-skill/SKILL.md": b"---\nname: a-skill\n"}))
    assert "ASKILL-P004" in codes(validate_skills(manifest_for("a-skill"), {"skills/a-skill/SKILL.md": b"---\ndescription: x\n---\n"}))
    assert "ASKILL-P005" in codes(validate_skills(manifest_for("a-skill"), {"skills/a-skill/SKILL.md": b"---\nname: a-skill\n---\n"}))
    assert "ASKILL-P008" in codes(validate_skills(manifest_for("a-skill", "a-skill"), skill("a-skill")))


def test_an_unregistered_skill_folder_is_refused():
    assert "TCC-S004" in codes(validate_skills(manifest_for("a-skill"), {**skill("a-skill"), **skill("stray")}))


@pytest.mark.parametrize(("path", "why"), [
    ("references/.hidden.md", "hidden"), ("references/..%2Fx.md", "unsafe"), ("references\\x.md", "backslash"),
    ("references/NUL.md", "reserved"), ("references/a$b.md", "unsafe"),
])
def test_an_unsafe_companion_path_is_refused(path, why):
    files = {**skill("a-skill"), f"skills/a-skill/{path}": b"x"}
    assert "TCC-S003" in codes(validate_skills(manifest_for("a-skill"), files)), why


def test_companion_limits_are_enforced():
    many = {**skill("a-skill"), **{f"skills/a-skill/references/f{i}.md": b"x" for i in range(21)}}
    assert "TCC-S002" in codes(validate_skills(manifest_for("a-skill"), many))
    twenty = {**skill("a-skill"), **{f"skills/a-skill/references/f{i}.md": b"x" for i in range(20)}}
    assert not errors(validate_skills(manifest_for("a-skill"), twenty))
    huge = {**skill("a-skill"), "skills/a-skill/references/big.md": b"x" * (5 * 1024 * 1024 + 1)}
    assert "TCC-S002" in codes(validate_skills(manifest_for("a-skill"), huge))


def test_a_skill_body_over_the_token_budget_is_refused():
    assert "TCC-S001" in codes(validate_skills(manifest_for("a-skill"), skill("a-skill", body="word " * 4500)))


def test_a_skill_naming_a_tool_that_does_not_exist_fails():
    assert "TCC-T001" in codes(validate_tools(skill("a-skill", "Call `client_summary` first.")))
    assert not validate_tools(skill("a-skill", "Call `client_situation` with a `client_id`."))


def test_a_skill_naming_a_tool_that_is_declared_but_not_built_fails(monkeypatch):
    spec = dataclasses.replace(catalog.BY_NAME["client_trend"], implemented=False)
    monkeypatch.setitem(catalog.BY_NAME, "client_trend", spec)
    assert "TCC-T002" in codes(validate_tools(skill("a-skill", "Call `client_trend`.")))


def test_a_skill_naming_plumbing_fails():
    assert "TCC-T002" in codes(validate_tools(skill("a-skill", "Call `claim_package_redeem`.")))


def test_a_write_named_without_its_pair_fails():
    assert "TCC-T003" in codes(validate_tools(skill("a-skill", "Call `engagement_set_prepare` and stop.")))
    assert "TCC-T003" in codes(validate_tools(skill("a-skill", "Call `engagement_set_commit` straight away.")))
    assert not validate_tools(skill("a-skill", "`engagement_set_prepare`, then `engagement_set_commit`."))


def test_neutrality_refuses_a_customer_name_an_identifier_and_a_real_address():
    deny_term = "exp" + "erian"
    files = {"skills/a/SKILL.md": f"Written for {deny_term} staff. Tenant 3f2a9c1e-1b2d-4e5f-8a9b-0c1d2e3f4a5b. Mail pat@contoso.onmicrosoft.com.".encode()}
    assert {"TCC-N001", "TCC-N002", "TCC-N003"} <= codes(validate_neutrality(files))
    clean = {"skills/a/SKILL.md": b"Placeholders only: 00000000-0000-0000-0000-000000000000 and pat@example.com."}
    assert not errors(validate_neutrality(clean))


def test_the_frontmatter_reader_handles_the_slice_skills_use_and_refuses_the_rest():
    head, body = frontmatter.split("---\nname: x\ndescription: |\n  one\n  two\nmetadata:\n  author: A\n  version: \"1.0\"\n---\nBody")
    parsed = frontmatter.parse(head)
    assert parsed == {"name": "x", "description": "one\ntwo", "metadata": {"author": "A", "version": "1.0"}} and body == "Body"
    assert frontmatter.parse("description: >\n  folded\n  text")["description"] == "folded text"
    for bad in ("tags: [a, b]", "name: &anchor x", "just text"):
        with pytest.raises(frontmatter.FrontmatterError):
            frontmatter.parse(bad)


# --------------------------------------------------------- the real skills, judged


def test_the_real_package_has_no_validation_errors(real):
    configured, manifest, files = real
    assert not errors(package.validate(manifest, files, configured))


def test_every_tool_a_skill_names_is_built_and_offered(real):
    offered = {s.name for s in catalog.offered()}
    named = set()
    for name, data in real[2].items():
        if name.startswith("skills/") and name.endswith(".md"):
            named |= {t for t in tool_references(data.decode("utf-8")) if t in catalog.BY_NAME}
    assert named and named <= offered
    assert all(catalog.BY_NAME[t].implemented for t in named)


def _used(files, skill_name):
    text = "\n".join(d.decode() for n, d in files.items() if n.startswith(f"skills/{skill_name}/") and n.endswith(".md"))
    return tool_references(text) & set(catalog.BY_NAME)


def test_the_book_review_uses_the_tools_the_workflow_names(real):
    used = _used(real[2], "tcc-book-review")
    assert {"book_rank", "client_resolve", "client_situation", "client_trend", "engagement_set_prepare", "engagement_set_commit", "verify_figures"} <= used


def test_the_review_pack_uses_the_tools_the_workflow_names(real):
    used = _used(real[2], "tcc-client-review-pack")
    assert {
        "client_resolve", "client_eligibility", "client_trend", "client_at_risk", "client_discovery", "simulate", "findings_list",
        "finding_resolve_prepare", "finding_resolve_commit", "claim_transition_prepare", "claim_transition_commit", "calc_walkthrough",
        "claim_package_create_prepare", "claim_package_create_commit", "claim_package_link", "verify_figures",
    } <= used


def test_the_shared_skill_covers_every_write_pair_and_both_workflows_point_at_it(real):
    files = real[2]
    pairs = {s.name for s in catalog.offered() if s.kind in (catalog.WRITE_PREPARE, catalog.WRITE_COMMIT)}
    assert pairs <= _used(files, "tcc-figures-and-writes")
    for workflow in ("tcc-book-review", "tcc-client-review-pack"):
        assert "tcc-figures-and-writes" in files[f"skills/{workflow}/SKILL.md"].decode()


def test_the_shared_rules_say_what_the_brief_requires(real):
    text = real[2]["skills/tcc-figures-and-writes/SKILL.md"].decode()
    for phrase in ("exactly as the tool returned it", "VERBATIM", "verify_figures", "`*_prepare`", "Never batch", "not tax advice"):
        assert phrase.lower() in text.lower(), phrase


def test_every_skill_body_stays_inside_the_budget_and_ends_with_its_checklist(real):
    for name in ("tcc-book-review", "tcc-client-review-pack"):
        text = real[2][f"skills/{name}/SKILL.md"].decode()
        assert len(text) / 4 < 5000
        assert "## Output checklist" in text and "## If something fails" in text


def test_the_shipped_skills_and_the_whole_source_tree_are_customer_neutral():
    sources = {p.relative_to(PLUGIN).as_posix(): p.read_bytes() for p in PLUGIN.rglob("*") if p.is_file()}
    assert sources and not errors(validate_neutrality(sources))


def test_the_manifest_template_renders_with_every_marker_filled(tmp_path):
    manifest = render_manifest(PLUGIN / "manifest.template.json", settings(tmp_path))
    assert "{{" not in json.dumps(manifest)


def test_every_offered_tool_carries_the_safety_annotations_cowork_needs():
    for spec in catalog.offered():
        annotations = describe(spec)["annotations"]
        assert "readOnlyHint" in annotations and "destructiveHint" in annotations, spec.name
        if spec.kind == catalog.READ:
            assert annotations["readOnlyHint"] is True and annotations["destructiveHint"] is False
        if spec.kind == catalog.WRITE_COMMIT:
            assert annotations["destructiveHint"] is True


# ------------------------------------------------------------ repository hygiene


def test_no_raster_or_pdf_file_is_tracked_or_sitting_in_the_plugin_folder():
    banned = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".pdf")
    on_disk = [p for p in PLUGIN.rglob("*") if p.suffix.lower() in banned]
    assert on_disk == []
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    if tracked.returncode == 0:
        assert [f for f in tracked.stdout.splitlines() if f.lower().endswith(banned)] == []


def test_dist_is_ignored_so_a_built_package_is_never_committed():
    ignored = subprocess.run(["git", "check-ignore", "-q", "dist/tcc-cowork-plugin.zip"], cwd=REPO)
    assert ignored.returncode in (0, 128) and (ignored.returncode == 0 or "dist/" in (REPO / ".gitignore").read_text(encoding="utf-8"))
