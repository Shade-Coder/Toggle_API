# API de Sincronización de Toggl Track

Este proyecto implementa una herramienta en Python para extraer y sincronizar datos desde la API de Toggl Track hacia una base de datos SQL Server y archivos CSV. La sincronización abarca workspaces, proyectos, usuarios y registros de tiempo.

## Requisitos Previos

- Python 3.8 o superior
- PowerShell 5.1 o superior (opcional para automatización)
- SQL Server 2016 o superior
- Acceso a la API de Toggl Track

## Instalación

1. Clonar el repositorio:

```bash
git clone https://github.com/Shade-Coder/Toggl_API.git
cd Toggl_API
```

2. Crear un entorno virtual de Python:

```bash
python -m venv venv
.\venv\Scripts\activate
```

3. Instalar dependencias:

```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
   - Copiar el archivo `.env.example` a `.env`
   - Actualizar las variables con los valores correspondientes

## Estructura del Proyecto

```
Toggl_API_Sync/
├── .env                      # Variables de entorno
├── requirements.txt          # Dependencias de Python
├── toggl_api.py              # Script principal de sincronización
├── Reports/                     # Carpeta para logs
└── csv_exports/              # Directorio de exportaciones CSV
```

## Configuración

### Variables de Entorno

```env
# API Toggl Track
TOGGL_API_TOKEN=Token_API

# Base de datos SQL Server
DB_SERVER=nombre_servidor
DB_DATABASE=nombre_base
DB_USERNAME=usuario
DB_PASSWORD=contraseña

# Configuración de la aplicación
LOG_FILE=logs/toggl_sync.log
LOG_LEVEL=INFO
EXPORT_CSV=True
EXPORT_DIR=csv_exports/
```

## Uso

### Ejecución Manual

Para ejecutar la sincronización manualmente:

```bash
python toggl_api.py
```

### Ejecución con PowerShell

Opcionalmente puedes crear un script `.ps1` similar al siguiente:

```powershell
python toggl_api.py
```

Y programarlo con el Programador de Tareas de Windows para una ejecución periódica.

## Estructura de la Base de Datos

### Tabla `toggl_workspace_projects`

```sql
CREATE TABLE dbo.toggl_workspace_projects (
    id BIGINT PRIMARY KEY,
    workspace_id BIGINT,
    client_id BIGINT,
    name NVARCHAR(255),
    is_private BIT,
    active BIT,
    at DATETIME,
    created_at DATETIME,
    server_deleted_at DATETIME,
    color NVARCHAR(50),
    billable BIT,
    template BIT,
    auto_estimates BIT,
    estimated_hours FLOAT,
    estimated_seconds INT,
    rate FLOAT,
    rate_last_updated DATETIME,
    currency NVARCHAR(10),
    recurring BIT,
    template_id BIGINT,
    recurring_parameters NVARCHAR(MAX),
    fixed_fee FLOAT,
    actual_hours FLOAT,
    actual_seconds INT,
    total_count INT,
    client_name NVARCHAR(255),
    can_track_time BIT,
    start_date DATE,
    status NVARCHAR(50),
    wid BIGINT,
    cid BIGINT,
    pinned BIT,
    fecha_actualizacion DATE,
    hora_actualizacion TIME
)
```

### Tabla `toggl_project_users` 

```sql
CREATE TABLE dbo.toggl_project_users (
    id BIGINT PRIMARY KEY,
    project_id BIGINT,
    user_id BIGINT,
    workspace_id BIGINT,
    manager BIT,
    rate FLOAT,
    rate_last_updated DATETIME,
    at DATETIME,
    group_id BIGINT,
    gid BIGINT,
    labor_cost FLOAT,
    labor_cost_last_updated DATETIME
)
```

### Tabla `toggl_time_entries` 

```sql
CREATE TABLE dbo.toggl_time_entries (
    user_id BIGINT,
    username NVARCHAR(255),
    project_id BIGINT,
    task_id BIGINT,
    billable BIT,
    description NVARCHAR(500),
    tag_ids NVARCHAR(MAX),
    billable_amount_in_cents INT,
    hourly_rate_in_cents INT,
    currency NVARCHAR(10),
    time_entry_id BIGINT,
    row_number INT
)
```
### Tabla `time_entries_dates` 

```sql
CREATE TABLE dbo.time_entries_dates (
    time_entry_id BIGINT PRIMARY KEY,
    seconds INT,
    start DATETIME,
    stop DATETIME,
    at DATETIME,
    at_tz NVARCHAR(50)
)
```

## Características

- Extracción de workspaces, proyectos, usuarios y registros de tiempo
- Autenticación básica vía token con Toggl Track
- Exportación automática a archivos CSV
- Logging detallado
- Manejo de errores controlado
- Inserciones seguras en base de datos

## Logs

Los logs se almacenan en el directorio `Reports/` con el formato .csv


## Manejo de Errores

Errores manejados por el sistema:

1. **APIError**: Fallos en la respuesta de la API
2. **DBConnectionError**: Problemas al conectar con SQL Server
3. **DataSyncError**: Fallos generales en la sincronización

## Mantenimiento

### Monitoreo

Se recomienda monitorear:

- Estado y contenido del último log
- Tamaño de la carpeta `Reports`
- Última ejecución registrada en la base de datos
- Errores en logs o tabla de auditoría (opcional)

## Soporte

Para reportar problemas o solicitar soporte, por favor crea un issue en el repositorio.
#Toggl_API