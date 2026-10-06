$ErrorActionPreference = 'Stop'
$legacyRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CephVR\runtime'))
$privateRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CephVR2\runtime'))
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$before = (Get-Acl -LiteralPath $legacyRoot).Sddl
$selected = @(Get-ChildItem -LiteralPath $legacyRoot -Force | Where-Object {
    $_.PSIsContainer -and ($_.Name -eq 'recovery' -or
        $_.Name -match '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
})
$records = @()
foreach ($item in $selected) {
    $source = [IO.Path]::GetFullPath($item.FullName)
    $target = [IO.Path]::GetFullPath((Join-Path $privateRoot $item.Name))
    if ([IO.Path]::GetDirectoryName($source) -ne $legacyRoot -or
        [IO.Path]::GetDirectoryName($target) -ne $privateRoot -or
        (Test-Path -LiteralPath $target)) { throw 'Unsafe or occupied migration path' }
    $entries = @($item) + @(Get-ChildItem -LiteralPath $source -Recurse -Force)
    foreach ($entry in $entries) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Runtime migration does not follow reparse points'
        }
        $acl = Get-Acl -LiteralPath $entry.FullName
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        if (-not $acl.AreAccessRulesProtected -or $rules.Count -ne 1 -or
            $rules[0].IdentityReference -ne $currentSid -or
            $rules[0].AccessControlType -ne 'Allow') {
            throw "Runtime entry is not protected owner-only: $($entry.FullName)"
        }
        $relative = $entry.FullName.Substring($legacyRoot.Length + 1)
        $digest = if ($entry.PSIsContainer) { $null } else {
            (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash
        }
        $records += [pscustomobject]@{relative=$relative; sddl=$acl.Sddl; sha256=$digest}
    }
}
foreach ($item in $selected) {
    Move-Item -LiteralPath $item.FullName -Destination (Join-Path $privateRoot $item.Name)
}
foreach ($record in $records) {
    $target = Join-Path $privateRoot $record.relative
    if ((Get-Acl -LiteralPath $target).Sddl -ne $record.sddl) {
        throw "Private ACL changed during migration: $($record.relative)"
    }
    if ($record.sha256 -and
        (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $record.sha256) {
        throw "Runtime content changed during migration: $($record.relative)"
    }
}
$legacyAcl = Get-Acl -LiteralPath $legacyRoot
$legacyAcl.SetAccessRuleProtection($true, $false)
$rule = [Security.AccessControl.FileSystemAccessRule]::new(
    $currentSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$legacyAcl.SetAccessRule($rule)
Set-Acl -LiteralPath $legacyRoot -AclObject $legacyAcl
[pscustomobject]@{
    date=(Get-Date -Format o); legacyRoot=$legacyRoot; privateRoot=$privateRoot
    legacyAclBefore=$before; legacyAclAfter=(Get-Acl -LiteralPath $legacyRoot).Sddl
    movedDirectories=@($selected.Name); verifiedPrivateEntries=$records.Count
    contentAndPrivateAclsPreserved=$true
} | ConvertTo-Json -Depth 4
