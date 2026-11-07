from flask import *
from funciones import *
from datetime import *
from db import mysql

def funcion_notificaciones(tiporol):
    
    if tiporol == 'colaborador':
        
        db = mysql.connection.cursor()
        id_colaborador = session["id_colaborador"]
        # Numero de notificaciones 
        notificaciones = 0
        # Id de la solicitud del colaborador 
        query="SELECT idsolicitudesprestamos FROM solicitudesprestamos WHERE idcolaborador = %s"

        db.execute(query,[id_colaborador])
        solicitud = db.fetchone()
        solicitud_id = solicitud[0] if solicitud else None

        # Estado de solicitud. En PostgreSQL es una funcion, no un procedimiento.
        estadosolicitud = False
        rows = []
        if solicitud_id is not None:
            query = "SELECT * FROM notificarestadosolicitud(%s)"
            db.execute(query,[solicitud_id])
            rows = db.fetchall()

        # Diccionario Estado de solicitud 
        columns = [column[0] for column in db.description]
        rows = [dict(zip(columns, row)) for row in rows]

        for row in rows:
            if row['Estado'] == 'A':
                estadosolicitud = "Aceptada"
                notificaciones += 1
            elif row['Estado'] == 'D':
                estadosolicitud = "Denegada"
                notificaciones += 1
            else:
                estadosolicitud=False

        # Fecha de Proximas Cuotas
        query = "SELECT * FROM mostrarfechascuotas(%s)"

        db.execute(query,[id_colaborador])
        rows = db.fetchall()

        # Diccionario de Fechas 
        columns = [column[0] for column in db.description]
        rows = [
            {columns[i]: (row[i].strftime('%d/%m/%Y') if isinstance(row[i], date) else row[i])
            for i in range(len(columns))}
            for row in rows
        ]

        # fecha actual formateada la fecha para mostrarla en día/mes/año
        fecha_actual = datetime.now()
        # Formatear la fecha para mostrarla en día/mes/año
        fecha_actual = fecha_actual.strftime('%d/%m/%Y')

        # Encuentra la siguiente fecha de pago
        siguiente_fecha_pago = False
        for pago in rows:
            fecha_pago = pago['FechaDePago']
            if fecha_pago < fecha_actual:
                siguiente_fecha_pago = fecha_pago
                notificaciones += 1
                break
        db.close()

        Todasnotificaciones = (siguiente_fecha_pago,estadosolicitud,notificaciones)
        return(Todasnotificaciones)
    
    elif tiporol == "admin":
        
        db = mysql.connection.cursor()
        id_administrador = session["id_administrador"]

        # Numero de notificaciones 
        notificaciones = 0

        # Notificar Fecha de registro de cuotas 
        fecha_actual = datetime.now()
        dia_actual = fecha_actual.day
        # Verificar si el día actual está en alguno de los rangos especificados
        if 13 <= dia_actual <= 15:
            reporte = "quincenal"
            notificaciones += 1
        elif 26 <= dia_actual <= 30:
            reporte = "mensual"
            notificaciones += 1
        else:
            reporte = False

        # Notificar solicitudes en espera 
        query="SELECT * FROM mostrarsolicitudespendientes(%s);"
        db.execute(query,[id_administrador])
        solicitudes = db.fetchall()

        numerodesolicitudes = 0

        for solicitudes in solicitudes:
            notificaciones += 1
            numerodesolicitudes += 1

        Todasnotificaciones = (notificaciones,numerodesolicitudes,reporte)

        db.close()
        return(Todasnotificaciones)
    