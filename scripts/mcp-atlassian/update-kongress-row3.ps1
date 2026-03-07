$ErrorActionPreference = 'Stop'

$base = 'https://devstack.vwgroup.com/confluence'
$pageId = '6952668174'
$token = $env:CONFLUENCE_PAT

if (-not $token) {
    throw 'CONFLUENCE_PAT ist nicht gesetzt.'
}

$headers = @{
    Authorization = "Bearer $token"
    Accept = 'application/json'
    'Content-Type' = 'application/json; charset=utf-8'
}

$page = Invoke-RestMethod -Method Get -Uri "$base/rest/api/content/$pageId?expand=body.storage,version" -Headers $headers
$storage = $page.body.storage.value

$pattern = '(?s)<tr class=""><td class="numberingColumn[^>]*>3</td>.*?</tr>'
$replacement = '<tr class=""><td class="numberingColumn highlight-#abf5d1" contenteditable="false" data-highlight-colour="#abf5d1" data-mce-resize="false">3</td><td>CAN- &amp; K2.0-Datenmodell dokumentierbar machen (XSD + Semantik)</td><td>Ziel: Modellwissen aus Code in nutzbare Doku ueberfuehren (Schema/XSD, Kernfelder, Beispiele). Use-Case: Effizienzgewinn fuer Entwickler und Spezifikateure durch schnellere Klaerung fachlicher Fragen via RAG/MCP und weniger Rueckfragen.</td><td>Tobias Mueller / Rainer Ganss</td><td>Workshop</td><td>60 Min</td></tr>'

$newStorage = [regex]::Replace($storage, $pattern, $replacement, 1)
if ($newStorage -eq $storage) {
    throw 'Tabellenzeile 3 konnte nicht ersetzt werden.'
}

$payloadObject = @{
    id = $page.id
    type = 'page'
    title = $page.title
    version = @{ number = ([int]$page.version.number + 1) }
    body = @{ storage = @{ value = $newStorage; representation = 'storage' } }
}

$payload = $payloadObject | ConvertTo-Json -Depth 20
$updated = Invoke-RestMethod -Method Put -Uri "$base/rest/api/content/$pageId" -Headers $headers -Body $payload

Write-Output "UPDATED_PAGE_ID=$($updated.id)"
Write-Output "NEW_VERSION=$($updated.version.number)"
Write-Output "URL=$base/pages/viewpage.action?pageId=$pageId"
