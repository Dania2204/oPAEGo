// Infraestructura de PAEGo en Azure (plataforma web Django + API para la app móvil).
//
// Decisiones:
// - App Service Linux (código Python, sin contenedor): Oryx instala
//   requirements.txt en cada despliegue y /home es persistente, así las fotos de
//   evidencia (MEDIA_ROOT) sobreviven a reinicios y despliegues.
// - PostgreSQL Flexible Server 17 (B1ms, Burstable): suficiente para el piloto.
// - Key Vault guarda los secretos (clave de Django, URL de la BD, clave de
//   Gemini); la app los lee con referencias de Key Vault usando una identidad
//   administrada asignada por el usuario. Ningún secreto queda en app settings.
// - Log Analytics + Application Insights para los registros (JSON por consola).
//
// Alcance de suscripción: crea el grupo de recursos rg-<environmentName>.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Nombre del entorno de azd (p. ej. paego-prod). Se usa en los nombres y etiquetas.')
param environmentName string

@minLength(1)
@description('Región principal. Azure for Students solo permite algunas regiones: revisar la política de la suscripción.')
param location string

@description('Región de PostgreSQL. Puede diferir de la principal si la cuota de la suscripción no lo permite allí.')
param postgresLocation string = location

@description('Usuario administrador de PostgreSQL.')
param postgresAdminUser string = 'paegoadmin'

@secure()
@minLength(12)
@description('Contraseña del administrador de PostgreSQL.')
param postgresAdminPassword string

@secure()
@minLength(50)
@description('DJANGO_SECRET_KEY. También firma los JWT: cambiarla cierra todas las sesiones.')
param djangoSecretKey string

@secure()
@description('Clave de Gemini para el asistente de nutrición (opcional; sin ella responde 503).')
param geminiApiKey string = ''

@secure()
@description('Clave Fernet que cifra las plantillas faciales (supervisor PAE). Sin ella no se inscriben rostros (503). Perderla deja ilegibles las plantillas guardadas.')
param biometriaClave string = ''

@description('Similitud coseno mínima para aceptar un reconocimiento facial (calibrar con el modelo de la app).')
param umbralSimilitudFacial string = '0.80'

@description('Orígenes permitidos por CORS (p. ej. la app Flutter compilada para web).')
param corsAllowedOrigins array = []

// F1 (gratis, 60 min de CPU al día, sin Always On) para el día a día; B1 para
// demostraciones y uso real. Se cambia sin redesplegar:
//   az appservice plan update -g rg-<entorno> -n <plan> --sku B1
@allowed(['F1', 'B1', 'B2'])
@description('Plan de App Service.')
param appServiceSku string = 'F1'

// Texto y no bool: azd sustituye las variables de main.parameters.json como texto.
@allowed(['true', 'false'])
@description('Cargar los datos de demostración (seed_demo) al arrancar.')
param seedDemo string = 'true'

var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module recursos 'resources.bicep' = {
  name: 'recursos-paego'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    postgresLocation: postgresLocation
    postgresAdminUser: postgresAdminUser
    postgresAdminPassword: postgresAdminPassword
    djangoSecretKey: djangoSecretKey
    geminiApiKey: geminiApiKey
    biometriaClave: biometriaClave
    umbralSimilitudFacial: umbralSimilitudFacial
    corsAllowedOrigins: corsAllowedOrigins
    seedDemo: seedDemo
    appServiceSku: appServiceSku
    tags: tags
  }
}

// Salidas que azd guarda en el entorno (.azure/<entorno>/.env).
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output WEB_URI string = recursos.outputs.webUri
output WEB_APP_NAME string = recursos.outputs.webAppName
output POSTGRES_HOST string = recursos.outputs.postgresHost
output AZURE_KEY_VAULT_NAME string = recursos.outputs.keyVaultName
output APP_SERVICE_PLAN_NAME string = recursos.outputs.planName
