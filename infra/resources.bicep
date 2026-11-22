// Recursos de PAEGo dentro del grupo de recursos (ver main.bicep).
// Nombres: az{prefijo}{token}, token = uniqueString(suscripción, grupo, región, entorno).

param environmentName string
param location string
param postgresLocation string
param postgresAdminUser string
@secure()
param postgresAdminPassword string
@secure()
param djangoSecretKey string
@secure()
param geminiApiKey string
param corsAllowedOrigins array
param seedDemo string
param appServiceSku string
param tags object

var token = uniqueString(subscription().id, resourceGroup().id, location, environmentName)
var nombreBaseDatos = 'pae_go'

// Roles integrados de Key Vault.
var rolSecretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
var rolSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'

// ── Identidad de la aplicación ──────────────────────────────────────────────
// Asignada por el usuario: existe antes que la web app, así los permisos sobre
// Key Vault ya están listos cuando la app resuelve sus secretos.
resource identidad 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'azid${token}'
  location: location
  tags: tags
}

// ── Monitoreo ───────────────────────────────────────────────────────────────
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'azlog${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'azai${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ── Key Vault (RBAC) ────────────────────────────────────────────────────────
resource kv 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: 'azkv${token}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    // La protección de purga no se desactiva (una vez activa no se puede quitar).
    enablePurgeProtection: true
    // App Service resuelve las referencias desde fuera de una red privada.
    publicNetworkAccess: 'Enabled'
  }
}

resource kvOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, identidad.id, rolSecretsOfficer)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolSecretsOfficer)
    principalId: identidad.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, identidad.id, rolSecretsUser)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolSecretsUser)
    principalId: identidad.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── PostgreSQL Flexible Server ──────────────────────────────────────────────
// B1ms con 32 GB: entra en la oferta gratuita de Azure for Students (750 h/mes
// de B1ms + 32 GB de almacenamiento y 32 GB de respaldo durante 12 meses).
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'azpg${token}'
  location: postgresLocation
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '17'
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32, autoGrow: 'Disabled' }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    authConfig: { activeDirectoryAuth: 'Disabled', passwordAuth: 'Enabled' }
  }
}

// Solo servicios de Azure (la regla 0.0.0.0 - 0.0.0.0 es la convención de Azure).
// Para conectarse desde un PC (pg_dump/pg_restore) agregar una regla temporal con su IP.
resource pgAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource baseDatos 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: nombreBaseDatos
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// ── Secretos ────────────────────────────────────────────────────────────────
resource secretoDjango 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: kv
  name: 'django-secret-key'
  properties: { value: djangoSecretKey }
}

resource secretoBaseDatos 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: kv
  name: 'database-url'
  properties: {
    // TLS obligatorio hacia PostgreSQL; la contraseña va codificada para la URL.
    value: 'postgres://${postgresAdminUser}:${uriComponent(postgresAdminPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/${nombreBaseDatos}?sslmode=require'
  }
}

resource secretoGemini 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = if (!empty(geminiApiKey)) {
  parent: kv
  name: 'gemini-api-key'
  properties: { value: geminiApiKey }
}

// ── App Service ─────────────────────────────────────────────────────────────
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'azsp${token}'
  location: location
  tags: tags
  kind: 'linux'
  sku: { name: appServiceSku, tier: appServiceSku == 'F1' ? 'Free' : 'Basic' }
  properties: { reserved: true } // Linux
}

var nombreWeb = 'azwa${token}'
var host = '${nombreWeb}.azurewebsites.net'
var referencia = 'https://${kv.name}${environment().suffixes.keyvaultDns}/secrets'

resource web 'Microsoft.Web/sites@2024-04-01' = {
  name: nombreWeb
  location: location
  // azd encuentra el servicio "web" de azure.yaml por esta etiqueta.
  tags: union(tags, { 'azd-service-name': 'web' })
  kind: 'app,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identidad.id}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: identidad.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.13'
      // F1 no admite Always On: la app se descarga tras ~20 min sin uso y la
      // primera petición siguiente tarda en responder (arranque en frío).
      alwaysOn: appServiceSku != 'F1'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      // migrate + createcachetable + collectstatic + gunicorn (backend/startup.sh).
      appCommandLine: 'bash startup.sh'
      cors: {
        allowedOrigins: corsAllowedOrigins
        supportCredentials: false
      }
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'DJANGO_SETTINGS_MODULE', value: 'config.settings.prod' }
        { name: 'DJANGO_SECRET_KEY', value: '@Microsoft.KeyVault(SecretUri=${referencia}/django-secret-key)' }
        { name: 'DATABASE_URL', value: '@Microsoft.KeyVault(SecretUri=${referencia}/database-url)' }
        {
          name: 'GEMINI_API_KEY'
          value: empty(geminiApiKey) ? '' : '@Microsoft.KeyVault(SecretUri=${referencia}/gemini-api-key)'
        }
        { name: 'DJANGO_ALLOWED_HOSTS', value: host }
        { name: 'DJANGO_CSRF_TRUSTED_ORIGINS', value: 'https://${host}' }
        { name: 'URL_PUBLICA', value: 'https://${host}' }
        { name: 'CORS_ALLOWED_ORIGINS', value: join(corsAllowedOrigins, ',') }
        // Contadores del límite de intentos compartidos entre workers de gunicorn.
        { name: 'CACHE_URL', value: 'dbcache://cache_paego' }
        { name: 'LOG_FORMATO', value: 'json' }
        // /home es almacenamiento persistente de App Service.
        { name: 'MEDIA_ROOT', value: '/home/paego/media' }
        { name: 'PAEGO_SEED_DEMO', value: seedDemo }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: insights.properties.ConnectionString }
      ]
    }
  }
  // Los secretos y los permisos deben existir antes de que la app los lea.
  dependsOn: [kvOfficer, kvUser, secretoDjango, secretoBaseDatos, pgAzure, baseDatos]
}

resource diagnosticoWeb 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diagnostico-paego'
  scope: web
  properties: {
    workspaceId: logs.id
    logs: [
      { category: 'AppServiceConsoleLogs', enabled: true }
      { category: 'AppServiceHTTPLogs', enabled: true }
      { category: 'AppServiceAppLogs', enabled: true }
      { category: 'AppServicePlatformLogs', enabled: true }
    ]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output webUri string = 'https://${web.properties.defaultHostName}'
output webAppName string = web.name
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output keyVaultName string = kv.name
output planName string = plan.name
