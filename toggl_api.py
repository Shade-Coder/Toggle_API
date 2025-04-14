import os
import requests
from dotenv import load_dotenv
import pandas as pd
import pyodbc
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import json
import ast

# Cargar variables de entorno
load_dotenv()

# Crear directorio Reports si no existe
REPORTS_DIR = "Reports"
if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)

# Parámetros de conexión SQL Server
SQL_SERVER = os.getenv('SQL_SERVER', 'localhost')
SQL_DATABASE = os.getenv('SQL_DATABASE', 'TogglDB')
SQL_USERNAME = os.getenv('SQL_USERNAME', '')
SQL_PASSWORD = os.getenv('SQL_PASSWORD', '')

# Debug: Imprimir variables de entorno (sin mostrar datos sensibles)
print("Variables de entorno cargadas:")
print(f"Token API existe: {'Sí' if os.getenv('TOGGL_API_TOKEN') else 'No'}")
print(f"Servidor SQL: {SQL_SERVER}")
print(f"Base de datos SQL: {SQL_DATABASE}")

class DatabaseManager:
    def __init__(self):
        self.conn_str = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={SQL_SERVER};'
            f'DATABASE={SQL_DATABASE};'
            'Trusted_Connection=yes;'
        )
        self.conn = None
        self.cursor = None

    def connect(self):
        try:
            self.conn = pyodbc.connect(self.conn_str)
            self.cursor = self.conn.cursor()
            print("Conexión exitosa a SQL Server")
        except Exception as e:
            print(f"Error al conectar a SQL Server: {str(e)}")
            raise

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            print("Conexión a la base de datos cerrada")

    def delete_existing_data(self):
        """Eliminar datos existentes de todas las tablas"""
        try:
            tables = ['toggl_workspace_projects', 'toggl_project_users', 'toggl_time_entries', 'time_entries_dates']
            for table in tables:
                delete_sql = f"DELETE FROM {table}"
                self.cursor.execute(delete_sql)
            self.conn.commit()
            print("Datos anteriores eliminados exitosamente")
        except Exception as e:
            print(f"Error al eliminar datos anteriores: {str(e)}")
            self.conn.rollback()
            raise

    def save_dataframe(self, df: pd.DataFrame, table_name: str):
        """Guardar DataFrame en tabla SQL Server"""
        try:
            # Convertir todas las columnas a tipo string para evitar problemas de tipo de datos
            for col in df.columns:
                df[col] = df[col].astype(str)

            # Agregar columnas de fecha y hora de actualización para workspace_projects
            if table_name == 'toggl_workspace_projects':
                current_datetime = datetime.now()
                df['fecha_actualizacion'] = current_datetime.strftime('%Y-%m-%d')
                df['hora_actualizacion'] = current_datetime.strftime('%H:%M:%S')

            # Verificar si la tabla existe
            check_table_sql = f"""
            SELECT COUNT(*) 
            FROM sys.tables 
            WHERE name = '{table_name}'
            """
            self.cursor.execute(check_table_sql)
            table_exists = self.cursor.fetchone()[0] > 0

            if table_exists:
                # Obtener columnas existentes
                get_columns_sql = f"""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{table_name}'
                """
                self.cursor.execute(get_columns_sql)
                existing_columns = [row[0] for row in self.cursor.fetchall()]
                
                # Agregar nuevas columnas si no existen
                for col in df.columns:
                    if col not in existing_columns:
                        add_column_sql = f"ALTER TABLE {table_name} ADD [{col}] NVARCHAR(MAX)"
                        self.cursor.execute(add_column_sql)
                self.conn.commit()
            else:
                # Crear tabla si no existe
                columns = [f"[{col}] NVARCHAR(MAX)" for col in df.columns]
                create_table_sql = f"""
                CREATE TABLE {table_name} (
                    {', '.join(columns)}
                )
                """
                self.cursor.execute(create_table_sql)
                self.conn.commit()

            # Insertar datos
            for _, row in df.iterrows():
                # Crear la sentencia INSERT con los nombres de columnas explícitos
                columns_str = ', '.join([f'[{col}]' for col in df.columns])
                placeholders = ','.join(['?' for _ in row])
                insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                self.cursor.execute(insert_sql, tuple(row))
            
            self.conn.commit()
            print(f"Datos guardados exitosamente: {len(df)} filas en {table_name}")
        except Exception as e:
            print(f"Error al guardar datos en {table_name}: {str(e)}")
            self.conn.rollback()
            raise

    def save_time_entries_data(self, df: pd.DataFrame):
        """Guardar datos de time entries en dos tablas separadas y archivos CSV"""
        try:
            # Crear tabla principal de time entries
            main_columns = [
                "[user_id] NVARCHAR(MAX)",
                "[username] NVARCHAR(MAX)",
                "[project_id] NVARCHAR(MAX)",
                "[task_id] NVARCHAR(MAX)",
                "[billable] NVARCHAR(MAX)",
                "[description] NVARCHAR(MAX)",
                "[tag_ids] NVARCHAR(MAX)",
                "[billable_amount_in_cents] NVARCHAR(MAX)",
                "[hourly_rate_in_cents] NVARCHAR(MAX)",
                "[currency] NVARCHAR(MAX)",
                "[time_entry_id] NVARCHAR(MAX)",
                "[row_number] NVARCHAR(MAX)"
            ]
            
            create_main_table_sql = f"""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'toggl_time_entries')
            CREATE TABLE toggl_time_entries (
                {', '.join(main_columns)}
            )
            """
            self.cursor.execute(create_main_table_sql)
            self.conn.commit()

            # Crear tabla de fechas de time entries
            dates_columns = [
                "[time_entry_id] NVARCHAR(MAX)",
                "[seconds] NVARCHAR(MAX)",
                "[start] NVARCHAR(MAX)",
                "[stop] NVARCHAR(MAX)",
                "[at] NVARCHAR(MAX)",
                "[at_tz] NVARCHAR(MAX)"
            ]
            
            create_dates_table_sql = f"""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'time_entries_dates')
            CREATE TABLE time_entries_dates (
                {', '.join(dates_columns)}
            )
            """
            self.cursor.execute(create_dates_table_sql)
            self.conn.commit()

            # Listas para almacenar datos para archivos CSV
            main_data_list = []
            dates_data_list = []

            # Procesar e insertar datos
            for _, row in df.iterrows():
                try:
                    # Procesar time entries primero para obtener el ID
                    time_entries_str = str(row.get('time_entries', '[]'))
                    time_entry_id = ''
                    try:
                        time_entries = ast.literal_eval(time_entries_str)
                        if isinstance(time_entries, list) and len(time_entries) > 0:
                            time_entry_id = str(time_entries[0].get('id', ''))
                    except Exception as e:
                        print(f"Error al procesar time entries para la fila {row.get('row_number', 'desconocida')}: {str(e)}")
                        continue

                    # Convertir todos los valores a strings y manejar valores NaN/None
                    main_data = [
                        str(row.get('user_id', '')),
                        str(row.get('username', '')),
                        str(row.get('project_id', '')),
                        str(row.get('task_id', '')),
                        str(row.get('billable', '')),
                        str(row.get('description', '')),
                        str(row.get('tag_ids', '')),
                        str(row.get('billable_amount_in_cents', '')),
                        str(row.get('hourly_rate_in_cents', '')),
                        str(row.get('currency', '')),
                        time_entry_id,  # Usar el ID de time_entries
                        str(row.get('row_number', ''))
                    ]
                    
                    # Agregar a la lista de datos principales para CSV
                    main_data_list.append(main_data)
                    
                    # Insertar datos principales
                    insert_main_sql = """
                    INSERT INTO toggl_time_entries 
                    (user_id, username, project_id, task_id, billable, description, 
                     tag_ids, billable_amount_in_cents, hourly_rate_in_cents, currency, 
                     time_entry_id, row_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    self.cursor.execute(insert_main_sql, main_data)
                    
                    # Procesar e insertar fechas de time entries
                    if time_entries and isinstance(time_entries, list):
                        for entry in time_entries:
                            dates_data = [
                                str(entry.get('id', '')),  # Usar el ID original del time entry
                                str(entry.get('seconds', '')),
                                str(entry.get('start', '')),
                                str(entry.get('stop', '')),
                                str(entry.get('at', '')),
                                str(entry.get('at_tz', ''))
                            ]
                            
                            # Agregar a la lista de datos de fechas para CSV
                            dates_data_list.append(dates_data)
                            
                            insert_dates_sql = """
                            INSERT INTO time_entries_dates 
                            (time_entry_id, seconds, start, stop, at, at_tz)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """
                            self.cursor.execute(insert_dates_sql, dates_data)
                        
                except Exception as e:
                    print(f"Error al procesar fila {row.get('row_number', 'desconocida')}: {str(e)}")
                    continue
            
            # Crear y guardar archivos CSV
            main_df = pd.DataFrame(main_data_list, columns=[
                'user_id', 'username', 'project_id', 'task_id', 'billable', 'description',
                'tag_ids', 'billable_amount_in_cents', 'hourly_rate_in_cents', 'currency',
                'time_entry_id', 'row_number'
            ])
            main_df.to_csv(os.path.join(REPORTS_DIR, 'time_entries.csv'), index=False)
            print(f"Archivo time_entries guardado en {os.path.join(REPORTS_DIR, 'time_entries.csv')}")

            dates_df = pd.DataFrame(dates_data_list, columns=[
                'time_entry_id', 'seconds', 'start', 'stop', 'at', 'at_tz'
            ])
            dates_df.to_csv(os.path.join(REPORTS_DIR, 'time_entries_dates.csv'), index=False)
            print(f"Archivo time_entries_dates guardado en {os.path.join(REPORTS_DIR, 'time_entries_dates.csv')}")
            
            self.conn.commit()
            print(f"Datos de time entries guardados exitosamente en ambas tablas")
        except Exception as e:
            print(f"Error al guardar datos de time entries: {str(e)}")
            self.conn.rollback()
            raise

class TogglAPI:
    def __init__(self):
        self.api_token = os.getenv('TOGGL_API_TOKEN')
        # URLs de las APIs de Toggl
        self.base_url = "https://api.track.toggl.com/api/v9"  # API principal de Toggl
        self.reports_url = "https://api.track.toggl.com/reports/api/v3"  # API de reportes de Toggl
        self.auth = (self.api_token, 'api_token')
        
        print("\nTogglAPI inicializado:")
        print(f"URL Base: {self.base_url}")
        print(f"URL de Reportes: {self.reports_url}")

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None, use_reports_api: bool = False) -> Dict:
        """Realizar petición HTTP a la API de Toggl"""
        base = self.reports_url if use_reports_api else self.base_url
        url = f"{base}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        print(f"\nRealizando petición a: {url}")
        print(f"Método: {method}")
        print(f"Headers: {headers}")
        if params:
            print(f"Parámetros: {params}")
        if json_data:
            print(f"Datos JSON: {json_data}")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=self.auth,
                headers=headers,
                params=params,
                json=json_data
            )
            print(f"Código de estado de respuesta: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Error en respuesta: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error al realizar petición a {endpoint}: {str(e)}")
            return {}

    def get_workspaces(self) -> List[Dict]:
        """
        Obtener todos los workspaces del usuario
        Endpoint: GET /workspaces
        Documentación: https://developers.track.toggl.com/docs/api/workspaces#get-workspaces
        """
        return self._make_request("GET", "workspaces")

    def get_workspace_projects(self, workspace_id: int) -> List[Dict]:
        """
        Obtener todos los proyectos de un workspace específico
        Endpoint: GET /workspaces/{workspace_id}/projects
        Documentación: https://developers.track.toggl.com/docs/api/projects#get-projects
        """
        return self._make_request("GET", f"workspaces/{workspace_id}/projects")

    def get_project_users(self, workspace_id: int) -> List[Dict]:
        """
        Obtener todos los usuarios asignados a proyectos en un workspace
        Endpoint: GET /workspaces/{workspace_id}/project_users
        Documentación: https://developers.track.toggl.com/docs/api/project_users#get-project-users
        """
        return self._make_request("GET", f"workspaces/{workspace_id}/project_users")

    def get_time_entries(self, workspace_id: int, start_date: str, end_date: str) -> Dict:
        """
        Obtener reporte detallado de time entries
        Endpoint: POST /workspace/{workspace_id}/search/time_entries
        Documentación: https://developers.track.toggl.com/docs/api/reports#get-time-entries
        """
        endpoint = f"workspace/{workspace_id}/search/time_entries"
        json_data = {
            "start_date": start_date,
            "end_date": end_date
        }
        return self._make_request("POST", endpoint, json_data=json_data, use_reports_api=True)

    def export_required_data(self, workspace_id: int, start_date: str, end_date: str) -> Dict:
        """
        Exportar solo los datos requeridos para un workspace
        Incluye:
        - Proyectos del workspace
        - Usuarios de proyectos
        - Entradas de tiempo
        """
        return {
            "workspace_projects": self.get_workspace_projects(workspace_id),
            "project_users": self.get_project_users(workspace_id),
            "time_entries": self.get_time_entries(workspace_id, start_date, end_date)
        }

def main():
    print("\nIniciando Exportador de Datos de Toggl API...")
    
    # Inicializar el cliente API y el administrador de base de datos
    toggl = TogglAPI()
    db = DatabaseManager()
    
    try:
        # Conectar a la base de datos
        db.connect()
        
        # Eliminar datos existentes
        db.delete_existing_data()
        
        # Obtener workspaces
        workspaces = toggl.get_workspaces()
        if workspaces:
            print("\nWorkspaces disponibles:")
            for workspace in workspaces:
                print(f"- {workspace.get('name', 'Desconocido')} (ID: {workspace.get('id', 'N/A')})")

            # Obtener datos del primer workspace
            workspace_id = workspaces[0].get('id')
            # Calcular fechas para últimos 6 meses
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)  # 6 meses = 180 días
            
            print(f"\nExportando datos para workspace {workspace_id}...")
            print(f"Período: {start_date.strftime('%Y-%m-%d')} a {end_date.strftime('%Y-%m-%d')}")
            
            data = toggl.export_required_data(
                workspace_id, 
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
            
            # Guardar datos en archivos CSV y base de datos
            for key, value in data.items():
                if isinstance(value, (list, dict)) and value:  # Solo guardar datos no vacíos
                    if isinstance(value, dict):
                        # Convertir diccionario único a lista para DataFrame
                        value = [value]
                    df = pd.DataFrame(value)
                    
                    # Guardar en CSV
                    filename = os.path.join(REPORTS_DIR, f"{key}.csv")
                    df.to_csv(filename, index=False)
                    print(f"Archivo {key} guardado en {filename}")
                    
                    # Guardar en base de datos
                    if key == "time_entries":
                        db.save_time_entries_data(df)
                    else:
                        table_name = f"toggl_{key}"
                        db.save_dataframe(df, table_name)
        else:
            print("No se encontraron workspaces. Por favor, verifica tu cuenta de Toggl.")
            
    except Exception as e:
        print(f"Ocurrió un error: {str(e)}")
    finally:
        # Cerrar conexión a la base de datos
        db.close()

if __name__ == "__main__":
    main() 