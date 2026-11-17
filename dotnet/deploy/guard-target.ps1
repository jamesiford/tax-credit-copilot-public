param([Parameter(Mandatory)][ValidateSet('api', 'gateway', 'worker', 'infrastructure')][string] $Service)
$ErrorActionPreference = 'Stop'
if ($Service -eq 'worker') { throw 'Worker App Service topology unavailable: no lifecycle-coupled HTTP health/progress seam.' }
if ($Service -eq 'infrastructure') {
    throw 'Provisioning is manual and separately approved. Configure the independent .NET backend and run the operator plan; this manifest never provisions automatically.'
}
if ($env:TCC_DOTNET_ACTIVATE -ne '1') { throw 'Explicit .NET application activation is required.' }
foreach ($key in @('DOTNET_ENVIRONMENT_NAME', 'DOTNET_RESOURCE_GROUP_NAME', 'DOTNET_TARGET_SUBSCRIPTION', 'GIT_COMMIT')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($key))) { throw "Required setting: $key" }
}
$suffix = $env:DOTNET_ENVIRONMENT_NAME
if ($suffix -cnotmatch '^[a-z][a-z0-9-]{2,19}$' -or
    $env:DOTNET_RESOURCE_GROUP_NAME -cne "rg-tcc-dotnet-$suffix" -or
    $env:GIT_COMMIT -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid independent .NET target identity or revision.' }
$key = "DOTNET_$($Service.ToUpperInvariant())_APP_NAME"
if ([Environment]::GetEnvironmentVariable($key) -cne "app-tcc-dotnet-$suffix-$Service") {
    throw "Invalid independent target setting: $key"
}
if (-not [guid]::TryParse($env:DOTNET_TARGET_SUBSCRIPTION, [ref]([guid]::Empty))) {
    throw 'Invalid DOTNET_TARGET_SUBSCRIPTION.'
}
if (($env:AZURE_SUBSCRIPTION_ID -and $env:AZURE_SUBSCRIPTION_ID -ine $env:DOTNET_TARGET_SUBSCRIPTION) -or
    ($env:AZURE_ENV_NAME -and $env:AZURE_ENV_NAME -cne $suffix) -or
    ($env:AZURE_RESOURCE_GROUP -and $env:AZURE_RESOURCE_GROUP -cne $env:DOTNET_RESOURCE_GROUP_NAME)) {
    throw 'Ambient azd target does not match the selected independent .NET target.'
}
function Invoke-AzMetadata([string[]] $Arguments) {
    $result = & az @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Native .NET target metadata could not be read.' }
    return ($result -join "`n")
}
$subscription = Invoke-AzMetadata @('account', 'show', '--query', 'id', '--output', 'tsv')
if ($subscription -cne $env:DOTNET_TARGET_SUBSCRIPTION) { throw 'OIDC account is not the selected .NET subscription.' }
$appName = [Environment]::GetEnvironmentVariable($key)
$common = @('--subscription', $env:DOTNET_TARGET_SUBSCRIPTION, '--resource-group', $env:DOTNET_RESOURCE_GROUP_NAME, '--name', $appName)
$raw = Invoke-AzMetadata (@('webapp', 'show') + $common + @('--query', '{id:id,reserved:reserved,tags:tags,identity:identity.type,public:publicNetworkAccess}', '--output', 'json'))
try { $app = $raw | ConvertFrom-Json -ErrorAction Stop }
catch { throw 'Native .NET target metadata could not be decoded.' }
$expected = "/subscriptions/$($env:DOTNET_TARGET_SUBSCRIPTION)/resourceGroups/$($env:DOTNET_RESOURCE_GROUP_NAME)/providers/Microsoft.Web/sites/$appName"
if ($app.id -ine $expected -or -not $app.reserved -or $app.public -ne 'Disabled' -or
    $app.identity -notlike '*UserAssigned*' -or $app.tags.'tcc-runtime' -cne 'dotnet' -or
    $app.tags.'tcc-ownership' -cne 'infra-dotnet' -or $app.tags.'azd-service-name' -cne "dotnet-$Service" -or
    $app.tags.'azd-env-name' -cne $suffix) { throw 'Native resource is not the approved private .NET target.' }
$raw = Invoke-AzMetadata (@('webapp', 'config', 'show') + $common + @('--query', '{stack:linuxFxVersion,start:appCommandLine}', '--output', 'json'))
try { $runtime = $raw | ConvertFrom-Json -ErrorAction Stop }
catch { throw 'Native runtime metadata could not be decoded.' }
$dll = @{ api = 'Api'; gateway = 'Gateway' }[$Service]
if ($runtime.stack -cne 'DOTNETCORE|10.0' -or $runtime.start -cne "dotnet TaxCredit.$dll.dll") {
    throw 'Native stack or DLL startup does not match the .NET package.'
}
$revision = Invoke-AzMetadata (@('webapp', 'config', 'appsettings', 'list') + $common + @('--query', "[?name=='GIT_COMMIT'].value | [0]", '--output', 'tsv'))
if ($revision -cne $env:GIT_COMMIT) { throw 'Operator-supplied runtime GIT_COMMIT does not match the artifact revision.' }
Write-Output "Native private .NET $Service target, identity, stack and revision assertions passed."
