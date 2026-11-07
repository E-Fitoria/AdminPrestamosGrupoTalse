from psycopg import connect
from psycopg.pq import TransactionStatus
from config import DatabaseConfig

class _ConnectionProxy:
    # crear coneccion a la base de datos mediante un proxy
    def __init__(self):
        self._conn = None
    
    # asegurar que la coneccion esta activa
    def _ensure(self):
        # si la coneccion no esta activa, crear una nueva
        if self._conn is None or self._conn.closed:
            self._conn = connect(DatabaseConfig.DATABASE_URL)
        
        return self._conn
    
    # pide una conexion valida a la base de datos y retorna un cursor que se puede usar para ejecutar consultas
    def cursor(self):
        conn = self._ensure()
        # Un error deja la transaccion abortada. La conexion es compartida,
        # asi que la siguiente consulta fallaria hasta hacer rollback.
        if conn.info.transaction_status == TransactionStatus.INERROR:
            conn.rollback()
        return conn.cursor()
    
    # confirma los cambios realizados en la base de datos
    def commit(self):
        self._ensure().commit()
    
    # deshace los cambios realizados en la base de datos
    def rollback(self):
        # si la coneccion esta activa, deshacer los cambios y no llama a ensure para no crear una nueva coneccion
        if self._conn is not None and not self._conn.closed:
            self._conn.rollback()
    
# clase que se encarga de la coneccion a la base de datos, aunque se usa postgres esto permite usar la misma interfaz de mysql para la base de datos 
# y no se necesita cambiar el codigo existente que usa mysql
class _MySQLCompat:
    connection = _ConnectionProxy()
    
mysql = _MySQLCompat()