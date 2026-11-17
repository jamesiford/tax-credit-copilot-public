"""Refuse live-provider test fixtures before Terraform can initialize a provider."""

from pathlib import Path
import re
import sys

RESOURCE_TYPES = {
    "azurerm_resource_group", "azurerm_service_plan",
    "azurerm_user_assigned_identity", "azurerm_role_assignment",
    "azurerm_linux_web_app", "azurerm_private_endpoint",
    "azurerm_monitor_diagnostic_setting",
}


def check_sources(sources):
    """Keep the mock boundary closed when a provider or fixture is added later."""
    failures = []
    tests = 0
    for path, original in sources.items():
        text = re.sub(r"/\*.*?\*/", "", original, flags=re.S)
        text = re.sub(r"(?m)^\s*(#|//).*?$", "", text)
        if path.endswith(".tf"):
            forbidden = r'(?m)^\s*(data|import|moved|removed|provisioner)\s+["{]'
            if re.search(forbidden, text) or re.search(r"\balias\s*=", text):
                failures.append(f"{path}: external reads, adoption, provisioners and aliases are forbidden")
            for name in re.findall(r'(?m)^\s*resource\s+"([^"]+)"', text):
                if name not in RESOURCE_TYPES:
                    failures.append(f"{path}: resource type is outside .NET ownership")
            for name in re.findall(r'(?m)^\s*provider\s+"([^"]+)"', text):
                if name != "azurerm":
                    failures.append(f"{path}: an unapproved provider was declared")
            for source in re.findall(r'\bsource\s*=\s*"([^"]+)"', text):
                if source != "hashicorp/azurerm" and not source.startswith("./modules/"):
                    failures.append(f"{path}: remote modules/providers are not approved")
        elif path.endswith(".tftest.hcl"):
            tests += 1
            mocks = re.findall(r'(?m)^\s*mock_provider\s+"([^"]+)"', text)
            if mocks != ["azurerm"]:
                failures.append(f"{path}: every fixture must declare exactly the azurerm mock")
            if re.search(r'(?m)^\s*provider\s+"|\bproviders\s*=|\balias\s*=', text):
                failures.append(f"{path}: real provider blocks, remapping and aliases are forbidden")
            runs = re.findall(r'(?m)^\s*run\s+"[^"]+"\s*{', text)
            commands = re.findall(r"(?m)^\s*command\s*=\s*(plan|apply)\s*$", text)
            if not runs or len(runs) != len(commands):
                failures.append(f"{path}: each run must explicitly select mocked plan/apply")
    if not tests:
        failures.append("No mocked Terraform tests found")
    return failures


def main():
    root = Path(__file__).resolve().parent
    sources = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and (path.name.endswith(".tf") or path.name.endswith(".tftest.hcl"))
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    }
    failures = check_sources(sources)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("Offline guard: only owned resource types; every test provider mocked; no aliases/adoption/hooks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
