<#
.SYNOPSIS
  Create (or update) a Foundry Model Gateway connection without putting a secret in the repo or in Terraform state. [AI-03]

.DESCRIPTION
  Bring-your-own-model lets Foundry prompt agents call models behind the customer's gateway: the agent's model
  becomes "<connection-name>/<model-name>". The documented way to create the connection from the command line is to
  deploy a Bicep template from microsoft-foundry/foundry-samples (infrastructure/infrastructure-setup-bicep/01-connections/):
  https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway

  This script wraps that deployment so the secret (an API key or an OAuth client secret) never touches disk in this
  repository and never appears in a tfvars file or state:

    * the secret comes from Key Vault (-KeyVaultName/-SecretName) or from an interactive secure prompt;
    * it is handed to the template through an environment variable read by a generated .bicepparam file (in the temp
      directory, deleted afterwards), not through a command-line argument another process could list;
    * the deployment is an ARM PUT, so running it twice is safe (idempotent).

  -WhatIf prints exactly what would run and fetches no secret. NOTHING here is run by the repository's tests against Azure.

.PARAMETER TemplateFile
  The Bicep template for your connection type, from the Foundry samples repository (ModelGateway for non-Azure gateways).
.PARAMETER Parameter
  The template's NON-secret parameters, by the names the template declares (connection name, target URL, models ...).
.PARAMETER SecretParameterName
  The template parameter that receives the secret. Check the template; the default is a guess.

.EXAMPLE
  ./create-model-connection.ps1 -ResourceGroup rg-tcc -TemplateFile ./modelgateway.bicep `
      -Parameter @{ connectionName = 'corp-gw'; targetUrl = 'https://gateway.example.com' } `
      -KeyVaultName kv-tcc -SecretName ai-gateway-api-key -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$TemplateFile,
    [Parameter(Mandatory)][hashtable]$Parameter,
    [string]$KeyVaultName,
    [string]$SecretName,
    [string]$SecretParameterName = 'apiKey',
    [string]$Subscription,
    [string]$DeploymentName = 'tcc-model-connection'
)

$ErrorActionPreference = 'Stop'
$secretVariable = 'TCC_GATEWAY_SECRET'

function ConvertTo-BicepLiteral([object]$Value) {
    if ($Value -is [bool]) { return $Value.ToString().ToLowerInvariant() }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [double]) { return "$Value" }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        return '[' + ((@($Value) | ForEach-Object { ConvertTo-BicepLiteral $_ }) -join ', ') + ']'
    }
    return "'" + ("$Value" -replace "'", "\'") + "'"
}

function Read-GatewaySecret {
    if ($KeyVaultName -and $SecretName) {
        $arguments = @('keyvault', 'secret', 'show', '--vault-name', $KeyVaultName, '--name', $SecretName, '--query', 'value', '-o', 'tsv')
        if ($Subscription) { $arguments += @('--subscription', $Subscription) }
        return (& az @arguments)
    }
    $secure = Read-Host -Prompt 'Gateway secret (input is hidden)' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

if (-not (Test-Path -LiteralPath $TemplateFile)) { throw "TemplateFile not found: $TemplateFile" }
if ($Parameter.ContainsKey($SecretParameterName)) { throw "Do not pass the secret in -Parameter; it is read separately." }

$template = (Resolve-Path -LiteralPath $TemplateFile).Path
$lines = @("using '$($template -replace '\\', '/')'") +
    ($Parameter.GetEnumerator() | Sort-Object Name | ForEach-Object { "param $($_.Name) = $(ConvertTo-BicepLiteral $_.Value)" }) +
    @("param $SecretParameterName = readEnvironmentVariable('$secretVariable')")
$parameterFile = Join-Path ([IO.Path]::GetTempPath()) ("tcc-model-connection-{0}.bicepparam" -f [guid]::NewGuid().ToString('N'))

$command = @('deployment', 'group', 'create', '--resource-group', $ResourceGroup, '--name', $DeploymentName, '--parameters', $parameterFile, '--only-show-errors')
if ($Subscription) { $command += @('--subscription', $Subscription) }

if (-not $PSCmdlet.ShouldProcess("resource group $ResourceGroup", "deploy the Foundry model connection from $TemplateFile")) {
    Write-Host "WhatIf: would write a temporary parameter file with:"
    $lines | ForEach-Object { Write-Host "  $_" }
    Write-Host "WhatIf: would read the secret from $(if ($KeyVaultName) { "Key Vault $KeyVaultName/$SecretName" } else { 'a secure prompt' }) into `$env:$secretVariable"
    Write-Host "WhatIf: would run: az $($command -join ' ')"
    return
}

try {
    Set-Content -LiteralPath $parameterFile -Value $lines -Encoding utf8
    Set-Item -Path "Env:$secretVariable" -Value (Read-GatewaySecret)
    & az @command
    if ($LASTEXITCODE -ne 0) { throw "az deployment group create failed with exit code $LASTEXITCODE" }
    Write-Host "Connection deployed. Verify it under Manage > Resource details > Admin-connected models, then set AI_FOUNDRY_CONNECTION_NAME."
}
finally {
    Remove-Item -LiteralPath $parameterFile -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "Env:$secretVariable" -ErrorAction SilentlyContinue
}
