#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OrdersUrl = "http://localhost:8001",
    [string]$InventoryUrl = "http://localhost:8002",
    [string]$Issuer = "http://localhost:8080/realms/microservices-lab",
    [int]$StockTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

$OrdersUrl = $OrdersUrl.TrimEnd("/")
$InventoryUrl = $InventoryUrl.TrimEnd("/")
$Issuer = $Issuer.TrimEnd("/")

$script:Passed = 0
$script:ProductId = $null
$script:OrderId = $null

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false

$http = [System.Net.Http.HttpClient]::new($handler)
$http.Timeout = [TimeSpan]::FromSeconds(20)

function Assert-Lab {
    param(
        [bool]$Condition,
        [string]$Description
    )

    if (-not $Condition) {
        throw $Description
    }

    $script:Passed++
    Write-Host "[OK] $Description" -ForegroundColor Green
}

function Invoke-LabHttp {
    param(
        [string]$Method,
        [string]$Url,
        [int]$Expected = 200,
        [string]$Token,
        [object]$Body = $null,
        [hashtable]$Form = $null,
        [switch]$Quiet
    )

    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method),
        $Url
    )
    $response = $null

    try {
        if ($Token) {
            $request.Headers.Authorization =
                [System.Net.Http.Headers.AuthenticationHeaderValue]::new(
                    "Bearer", $Token
                )
        }

        if ($null -ne $Form) {
            $fields =
                [System.Collections.Generic.Dictionary[string,string]]::new()

            foreach ($key in $Form.Keys) {
                $fields.Add([string]$key, [string]$Form[$key])
            }

            $request.Content =
                [System.Net.Http.FormUrlEncodedContent]::new($fields)
        }
        elseif ($null -ne $Body) {
            $json = ConvertTo-Json -InputObject $Body -Depth 10 -Compress

            $request.Content = [System.Net.Http.StringContent]::new(
                $json,
                [System.Text.Encoding]::UTF8,
                "application/json"
            )
        }

        $response = $http.SendAsync($request).GetAwaiter().GetResult()
        $status = [int]$response.StatusCode
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()

        # No imprimir cuerpos: una respuesta puede contener tokens.
        if ($status -ne $Expected) {
            throw "$Method $Url : esperado HTTP $Expected, recibido $status."
        }

        $headers = @{}
        foreach ($header in $response.Headers) {
            $headers[$header.Key] = $header.Value -join ","
        }

        $data = $null
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            try {
                $data = ConvertFrom-Json -InputObject $text
            }
            catch {
                throw "$Method $Url devolvio contenido que no es JSON."
            }
        }

        if (-not $Quiet) {
            Assert-Lab $true "$Method $Url -> HTTP $Expected"
        }

        return [pscustomobject]@{
            Status  = $status
            Data    = $data
            Headers = $headers
        }
    }
    finally {
        if ($null -ne $response) {
            $response.Dispose()
        }
        $request.Dispose()
    }
}

function Get-LabToken {
    param(
        [string]$ClientId,
        [string]$ClientSecret,
        [string]$Scope
    )

    $result = Invoke-LabHttp `
        -Method POST `
        -Url "$Issuer/protocol/openid-connect/token" `
        -Form @{
            grant_type    = "client_credentials"
            client_id     = $ClientId
            client_secret = $ClientSecret
            scope         = $Scope
        }

    $token = [string]$result.Data.access_token

    Assert-Lab `
        (-not [string]::IsNullOrWhiteSpace($token)) `
        "Token obtenido para $ClientId, sin mostrarlo"

    return $token
}

try {
    Write-Host "`nLAB 5: seguridad y flujo de negocio" -ForegroundColor Cyan
    Write-Host "Se crearan un producto y un pedido nuevos."
    Write-Host "Usa Inventario real, no el overlay de caos.`n"

    # 1. Salud publica y disponibilidad de Keycloak.
    $r = Invoke-LabHttp GET "$OrdersUrl/health"
    Assert-Lab ($r.Data.status -eq "healthy") "Pedidos saludable"

    $r = Invoke-LabHttp GET "$InventoryUrl/health"
    Assert-Lab ($r.Data.status -eq "healthy") "Inventario saludable"

    $r = Invoke-LabHttp GET "$Issuer/.well-known/openid-configuration"
    Assert-Lab ($r.Data.issuer -eq $Issuer) "Issuer de Keycloak correcto"

    # 2. Identidades de operador, lectura y servicio.
    # Secretos exclusivos del laboratorio local.
    $admin = Get-LabToken `
        "lab-admin-client" `
        "lab-admin-secret" `
        "orders.read orders.write inventory.read inventory.write ops.admin"

    $readonly = Get-LabToken `
        "readonly-client" `
        "readonly-secret" `
        "orders.read inventory.read"

    $service = Get-LabToken `
        "order-service-client" `
        "order-svc-secret-lab" `
        "inventory.read"

    # 3. Sin token, token invalido y permisos de lectura/escritura.
    $resources = @(
        "$OrdersUrl/api/v1/orders",
        "$InventoryUrl/api/v1/products"
    )

    foreach ($url in $resources) {
        $r = Invoke-LabHttp GET $url -Expected 401

        $r = Invoke-LabHttp GET $url `
            -Expected 401 `
            -Token "invalid.jwt.token"

        $r = Invoke-LabHttp GET $url -Token $readonly

        $r = Invoke-LabHttp POST $url `
            -Expected 403 `
            -Token $readonly `
            -Body @{}
    }

    # 4. El token de servicio sirve para Inventory, no para Orders.
    $r = Invoke-LabHttp GET "$InventoryUrl/api/v1/products" `
        -Token $service

    $r = Invoke-LabHttp GET "$OrdersUrl/api/v1/orders" `
        -Expected 401 `
        -Token $service

    $r = Invoke-LabHttp POST "$InventoryUrl/api/v1/products" `
        -Expected 403 `
        -Token $service `
        -Body @{}

    $r = Invoke-LabHttp GET "$OrdersUrl/api/v1/auth/me" `
        -Token $admin

    $r = Invoke-LabHttp GET "$InventoryUrl/api/v1/auth/me" `
        -Token $admin

    # 5. Observabilidad protegida.
    $r = Invoke-LabHttp GET "$OrdersUrl/health/circuit-breakers" `
        -Expected 403 `
        -Token $readonly

    $r = Invoke-LabHttp GET "$OrdersUrl/health/circuit-breakers" `
        -Token $admin

    # 6. Crear producto real con 20 unidades.
    $sku = "AUTH-" + [guid]::NewGuid().ToString("N").Substring(0, 12).ToUpperInvariant()

    $r = Invoke-LabHttp POST "$InventoryUrl/api/v1/products" `
        -Expected 201 `
        -Token $admin `
        -Body @{
            name           = "Producto PowerShell Lab05"
            sku            = $sku
            stock_quantity = 20
        }

    $script:ProductId = [string]$r.Data.id

    Assert-Lab `
        (-not [string]::IsNullOrWhiteSpace($script:ProductId)) `
        "Producto creado"

    $r = Invoke-LabHttp GET `
        "$InventoryUrl/api/v1/products/$script:ProductId" `
        -Token $readonly

    Assert-Lab ($r.Data.stock_quantity -eq 20) "Stock inicial: 20"

    # 7. Crear pedido.
    # Orders debe obtener su propio token para consultar Inventory.
    $customerId = [guid]::NewGuid().ToString()

    $r = Invoke-LabHttp POST "$OrdersUrl/api/v1/orders" `
        -Expected 201 `
        -Token $admin `
        -Body @{
            customer_id = $customerId
            items = @(
                @{
                    product_id = $script:ProductId
                    quantity   = 2
                    unit_price = "10.00"
                }
            )
        }

    $script:OrderId = [string]$r.Data.id

    Assert-Lab `
        (-not [string]::IsNullOrWhiteSpace($script:OrderId)) `
        "Pedido creado"

    Assert-Lab `
        ($r.Headers["X-Stock-Precheck"] -eq "verified") `
        "Precheck autenticado contra Inventario real: verified"

    Assert-Lab ($r.Data.status -eq "pending") "Estado inicial: pending"
    Assert-Lab ($r.Data.total -ceq "20.00") "Total exacto: 20.00"

    $r = Invoke-LabHttp GET "$OrdersUrl/api/v1/orders/$script:OrderId" `
        -Token $readonly

    Assert-Lab `
        ($r.Data.id -eq $script:OrderId -and $r.Data.total -ceq "20.00") `
        "Pedido consultable mediante la proyeccion"

    # 8. Esperar la reserva asincrona.
    # NO invocar /reservations manualmente: duplicaria la intencion.
    Write-Host "`nEsperando reserva por Kafka..." -ForegroundColor Cyan

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $stock = $null

    do {
        $r = Invoke-LabHttp GET `
            "$InventoryUrl/api/v1/products/$script:ProductId" `
            -Token $readonly `
            -Quiet

        $stock = $r.Data.stock_quantity

        if ($stock -eq 18) {
            break
        }

        if ($watch.Elapsed.TotalSeconds -ge $StockTimeoutSeconds) {
            throw "No se observo stock 18. Stock actual: $stock. Revisa outbox, Kafka y consumidor de Inventario."
        }

        Start-Sleep -Milliseconds 500
    } while ($true)

    Assert-Lab ($stock -eq 18) "Reserva automatica: stock 20 -> 18"

    # 9. Stock insuficiente conocido: rechazo antes de crear.
    $r = Invoke-LabHttp POST "$OrdersUrl/api/v1/orders" `
        -Expected 409 `
        -Token $admin `
        -Body @{
            customer_id = [guid]::NewGuid().ToString()
            items = @(
                @{
                    product_id = $script:ProductId
                    quantity   = 100
                    unit_price = "10.00"
                }
            )
        }

    Assert-Lab `
        ($r.Data.code -eq "INSUFFICIENT_STOCK") `
        "Precheck rechaza stock insuficiente"

    $r = Invoke-LabHttp GET `
        "$InventoryUrl/api/v1/products/$script:ProductId" `
        -Token $readonly

    Assert-Lab ($r.Data.stock_quantity -eq 18) "Stock conservado tras rechazo"

    # 10. Expiracion real: token firmado por Keycloak con TTL de 2 segundos.
    $short = Get-LabToken `
        "expiry-test-client" `
        "expiry-test-secret" `
        "orders.read"

    $r = Invoke-LabHttp GET "$OrdersUrl/api/v1/orders" -Token $short

    Write-Host "`nEsperando expiracion del token de prueba..."
    Start-Sleep -Seconds 3

    $r = Invoke-LabHttp GET "$OrdersUrl/api/v1/orders" `
        -Expected 401 `
        -Token $short

    # 11. La reserva no confirma automaticamente la orden.
    $r = Invoke-LabHttp GET "$OrdersUrl/api/v1/orders/$script:OrderId" `
        -Token $readonly

    Assert-Lab `
        ($r.Data.status -eq "pending") `
        "Pedido sigue pending: el laboratorio no implementa saga"

    Write-Host "`nLAB 5 APROBADO: $script:Passed comprobaciones." -ForegroundColor Green
    Write-Host "Producto: $script:ProductId"
    Write-Host "Pedido:   $script:OrderId"
    Write-Host "Resultado: pedido pending, total 20.00, stock 18."
    Write-Host "Datos de ensayo conservados. Tokens no mostrados ni guardados."
    exit 0
}
catch {
    Write-Host "`nLAB 5 NO APROBADO." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Comprobaciones correctas: $script:Passed"

    if ($script:ProductId) {
        Write-Host "Producto creado: $script:ProductId"
    }
    if ($script:OrderId) {
        Write-Host "Pedido creado: $script:OrderId"
    }

    Write-Host "Los datos ya creados permanecen para diagnostico."
    exit 1
}
finally {
    $http.Dispose()
    $handler.Dispose()
}