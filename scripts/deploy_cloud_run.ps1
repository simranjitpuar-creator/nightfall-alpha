[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')]
    [string]$ProjectId,

    [ValidatePattern('^[a-z][a-z0-9-]{0,61}[a-z0-9]$')]
    [string]$ServiceName = 'nightfall-alpha',

    [string]$Region = 'us-central1',

    [string]$BucketName = '',

    [string]$RepositoryName = 'nightfall-alpha'
)

$ErrorActionPreference = 'Stop'
$SecretName = 'nightfall-alpha-write-token'
$ServiceAccountName = "$ServiceName-runtime"
$ServiceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'Google Cloud CLI (gcloud) is required. Install it, then run gcloud auth login before this script.'
}

if (-not $BucketName) {
    $BucketName = "$ProjectId-nightfall-alpha-data"
}

function Invoke-Gcloud {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed: gcloud $($Arguments -join ' ')"
    }
}

$activeAccount = (& gcloud auth list --filter=status:ACTIVE --format='value(account)' | Select-Object -First 1)
if (-not $activeAccount) {
    throw 'No active gcloud account was found. Run gcloud auth login first.'
}

Write-Host "Deploying as $activeAccount to project $ProjectId in $Region"

Invoke-Gcloud @('services', 'enable', 'run.googleapis.com', 'cloudbuild.googleapis.com', 'artifactregistry.googleapis.com', 'secretmanager.googleapis.com', 'storage.googleapis.com', "--project=$ProjectId")

& gcloud artifacts repositories describe $RepositoryName "--location=$Region" "--project=$ProjectId" *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Gcloud @('artifacts', 'repositories', 'create', $RepositoryName, '--repository-format=docker', "--location=$Region", "--project=$ProjectId")
}

& gcloud storage buckets describe "gs://$BucketName" "--project=$ProjectId" *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Gcloud @('storage', 'buckets', 'create', "gs://$BucketName", "--location=$Region", '--uniform-bucket-level-access', "--project=$ProjectId")
}

& gcloud iam service-accounts describe $ServiceAccount "--project=$ProjectId" *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Gcloud @('iam', 'service-accounts', 'create', $ServiceAccountName, '--display-name=NightFall Alpha Cloud Run', "--project=$ProjectId")
}

Invoke-Gcloud @('storage', 'buckets', 'add-iam-policy-binding', "gs://$BucketName", "--member=serviceAccount:$ServiceAccount", '--role=roles/storage.objectUser', "--project=$ProjectId")

& gcloud secrets describe $SecretName "--project=$ProjectId" *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Gcloud @('secrets', 'create', $SecretName, '--replication-policy=automatic', "--project=$ProjectId")
}

$secureToken = Read-Host 'Choose the private write token you will enter before running simulations' -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$temporaryTokenFile = Join-Path ([IO.Path]::GetTempPath()) ("nightfall-alpha-token-{0}.txt" -f [guid]::NewGuid())
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($plainToken) -or $plainToken.Length -lt 16) {
        throw 'The write token must contain at least 16 characters.'
    }
    [IO.File]::WriteAllText($temporaryTokenFile, $plainToken, [Text.UTF8Encoding]::new($false))
    Invoke-Gcloud @('secrets', 'versions', 'add', $SecretName, "--data-file=$temporaryTokenFile", "--project=$ProjectId")
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    $plainToken = $null
    if (Test-Path -LiteralPath $temporaryTokenFile) {
        Remove-Item -LiteralPath $temporaryTokenFile -Force
    }
}

Invoke-Gcloud @('secrets', 'add-iam-policy-binding', $SecretName, "--member=serviceAccount:$ServiceAccount", '--role=roles/secretmanager.secretAccessor', "--project=$ProjectId")

$image = "$Region-docker.pkg.dev/$ProjectId/$RepositoryName/app:latest"
Invoke-Gcloud @('builds', 'submit', '.', "--tag=$image", "--project=$ProjectId")

$volume = "mount-path=/var/lib/nightfall-alpha,type=cloud-storage,bucket=$BucketName,readonly=false,mount-options=uid=10001;gid=10001"
$deployArguments = @(
    'run', 'deploy', $ServiceName,
    "--image=$image",
    "--region=$Region",
    "--project=$ProjectId",
    '--platform=managed',
    '--allow-unauthenticated',
    "--service-account=$ServiceAccount",
    '--port=8080',
    '--cpu=1',
    '--memory=2Gi',
    '--min=0',
    '--max=1',
    '--concurrency=1',
    '--timeout=900',
    '--execution-environment=gen2',
    '--set-env-vars=NIGHTFALL_ALPHA_ENV=production,NIGHTFALL_ALPHA_DATA_DIR=/var/lib/nightfall-alpha',
    "--set-secrets=NIGHTFALL_ALPHA_WRITE_TOKEN=${SecretName}:latest",
    '--add-volume', $volume,
    '--quiet'
)
Invoke-Gcloud $deployArguments

$serviceUrl = (& gcloud run services describe $ServiceName "--region=$Region" "--project=$ProjectId" --format='value(status.url)')
if (-not $serviceUrl) {
    throw 'Deployment completed, but the service URL could not be read.'
}

$health = Invoke-WebRequest -Uri "$serviceUrl/api/health" -UseBasicParsing
if ($health.StatusCode -ne 200) {
    throw "Health check failed with HTTP $($health.StatusCode)."
}

Write-Host "NightFall Alpha is live: $serviceUrl"
Write-Host 'The write token is required only for simulations, downloads, and other saved-data changes.'
