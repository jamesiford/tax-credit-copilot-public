# Shared by run-local.ps1 and configure-local.ps1: turns backend\.env into the .NET host's settings.

function Read-DotEnv([string]$Path) {
    $map = @{}
    if (Test-Path $Path) {
        Get-Content $Path | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' } | ForEach-Object {
            $k, $v = $_ -split '=', 2
            $map[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
        }
    }
    return $map
}

function Get-TaxCreditLocalEnvironment {
    param(
        [ValidateSet('live', 'offline')][string]$Mode = 'live',
        [ValidateSet('sqlite', 'warehouse')][string]$Persistence = 'sqlite'
    )
    $repo = Split-Path $PSScriptRoot -Parent
    $settings = [ordered]@{ ENVIRONMENT = 'local' }

    if ($Mode -eq 'offline') {
        $settings.AUTH_MODE = 'none'
        $settings.DATA_SOURCE = 'csv'
        $settings.TCC_PERSISTENCE_PROVIDER = 'sqlite'
        $settings.ARTIFACT_STORE = 'local'
        return $settings
    }

    $envFile = Join-Path $repo 'backend\.env'
    $cfg = Read-DotEnv $envFile
    foreach ($required in 'LAKEHOUSE_SQL_SERVER', 'LAKEHOUSE_SQL_DATABASE') {
        if (-not $cfg[$required]) { throw "$required is missing from $envFile" }
    }
    $settings.AUTH_MODE = if ($cfg['AUTH_MODE']) { $cfg['AUTH_MODE'] } else { 'none' }
    $settings.DATA_SOURCE = 'lakehouse'
    $settings.SOURCE_SQL_SERVER = $cfg['LAKEHOUSE_SQL_SERVER']
    $settings.SOURCE_SQL_DATABASE = $cfg['LAKEHOUSE_SQL_DATABASE']
    if ($cfg['SOURCE_SCHEMA']) { $settings.SOURCE_SCHEMA = $cfg['SOURCE_SCHEMA'] }
    # The sealed workspace routes refuse with a 503 when a lakehouse source has no workspace and lakehouse names, which leaves the portal on
    # "Workspace unavailable"; carry them through from backend\.env as the Python product does.
    foreach ($name in 'FABRIC_WORKSPACE', 'FABRIC_LAKEHOUSE', 'ONELAKE_ENDPOINT', 'REFERENCE_ACCOUNT_ID') {
        if ($cfg[$name]) { $settings[$name] = $cfg[$name] }
    }
    $settings.ARTIFACT_STORE = 'local'
    # DefaultAzureCredential would otherwise try Visual Studio / VS Code sign-ins first, which may be a different account.
    $settings.AZURE_TOKEN_CREDENTIALS = 'AzureCliCredential'
    $settings.TCC_PERSISTENCE_PROVIDER = $Persistence
    if ($Persistence -eq 'warehouse') {
        foreach ($required in 'WAREHOUSE_SERVER', 'WAREHOUSE_DATABASE') {
            if (-not $cfg[$required]) { throw "$required is missing from $envFile" }
        }
        $settings.FABRIC_SQL_SERVER = $cfg['WAREHOUSE_SERVER']
        $settings.FABRIC_SQL_DATABASE = $cfg['WAREHOUSE_DATABASE']
    }
    return $settings
}
