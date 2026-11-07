import io
from flask import *
from funcioncrearreportededucciones import crearreportededucciones
from funcioncrearreporteprestamo import reporteprestamo
from funcioncontrato import crear_contrato_prestamo
from funcion_notificaciones import funcion_notificaciones
from funciones import *
from db import mysql
from config import *
from funcionesGmail import send_mail_google
from funcionesLogin import sesion_colaborador,sesion_admin
from datetime import *
import calendar
import json

#configuracion de flask 
try:
    app = Flask(__name__)
    app.config.from_object(FlaskConfig)
except Exception as ex:
    print("Error durante la configuracion de Flask {}".format(ex))

# Configuración de Passlib para encriptar las password
contexto = PasslibConfig.CONTEXT

# Configuración de MySQL
try:
    if not DatabaseConfig.DATABASE_URL:
        raise ValueError("DATABASE_URL no esta definida en .env")
    _c = mysql.connection.cursor() # dispeara la coneccion usando ensure
    _c.execute("SELECT 1") # prueba de coneccion
    _c.close() # cierra el cursor
except Exception as ex:
    print("Error durante la conexión: {}".format(ex))

# Formato Json
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)

@app.route('/', methods=['GET', 'POST'])
def login():

    session.clear()
    db = mysql.connection.cursor()
    
    if request.method == 'POST':
        
        role = request.form.get('rol')

        if role == 'colaborador':
            # Procesar los datos del colaborador (cedula y contraseña)
            cedula = request.form.get('cedula')
            contrasena = request.form.get('contrasena_colaborador')
            
            #  Funcion para verificar login
            if sesion_colaborador(cedula,contrasena,db):
                
                session["CedulaColaborador"] = cedula
                colaborador = "colaborador"
                query = "SELECT idcolaborador,idsucursal,nombrescolaborador FROM colaboradores WHERE cedulacolaborador = %s"
                db.execute(query,(cedula,))
                rows = db.fetchone()
                session["id_colaborador"] = rows[0]
                session["id_sucursal_colaborador"] = rows[1]
                session["usuario_colaborador"] = rows[2]
                session["type"] =  colaborador
                
                if len(contrasena) < 8:
                    session['primera_contrasena'] = True

                return redirect(url_for('index'))
            
            else:
                flash('La cedula o contraseña incorrecta', 'error')
                return render_template('login.html')
            
        elif role == 'administrador':
            
            # Procesar los datos del administrador (usuario y contraseña)
            usuario = request.form.get('usuario')
            contrasena = request.form.get('contrasena_administrador')

            # Funcion para verificar login
            if sesion_admin(usuario,contrasena,db):
                
                admin =  "admin"
                # necesitamos tomar idAdministrador y idSucursal para las sesiones
                query = """
                    SELECT idadministrador, cedulaadministrador, idsucursal
                    FROM administrador
                    WHERE usuario = %s AND estadoadministrador = %s
                """
                db.execute(query,(usuario,'1'))
                rows = db.fetchone()
            
                session["id_administrador"] = rows[0]
                session["cedula_administrador"] = rows[1]
                session["id_sucursal_admin"] = rows[2]
                session["usuario"] = usuario
                session["type"] = admin
                
                if len(contrasena) < 8 and session["cedula_administrador"] != "000-000000-0000A":
                    session['primera_contrasena'] = True

                db.close()
                if session["cedula_administrador"] == "000-000000-0000A":
                    return redirect(url_for('dashboard'))
                return redirect(url_for('index'))
                
            else:
                flash('Contraseña o usuario incorrecto', 'error')
                return render_template('login.html')
            
    return render_template('login.html')

@app.route("/index", methods=['GET', 'POST'])
def index():
    # modal para enviar alerta de contrasena insegura
    show_modal = session.get('primera_contrasena', False)

    # Carga de notificaciones
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    if request.method == "GET":
        return render_template('index.html',notificacionesIndex=notificacionesIndex,show_modal=show_modal)

@app.route("/dashboard", methods=['GET','POST'])
def dashboard():
    # Conexion con la Bd
    db = mysql.connection.cursor()
    # Ultimos Prestamos Creados 
    query = "SELECT * FROM ultimosprestamoscreados();"
    db.execute(query)
    rows = crear_diccionario(db)

    # Colaboradores por Unidad De Negocio
    query = "SELECT * FROM numerodecolaboradoresporunidaddenegocio();"
    db.execute(query)
    Colaboradores = crear_diccionario(db)

    nombres = [unidad['nombreUnidadDeNegocio'] for unidad in Colaboradores]
    Numerocolaboradores = [unidad['NumeroDeColaboradores'] for unidad in Colaboradores]

    # Capital Prestado por Unidad de Negocio 
    query = "SELECT * FROM capitalprestadoporunidaddenegocio();"
    db.execute(query)
    Capital = crear_diccionario(db)

    # Crear un diccionario con todas las unidades de negocio y montos iniciales en 0
    unidades_negocio_capital = {
        # 'Mi Ranchito'
        'Mi viejo Ranchito': 0,
        'El Zocalo': 0,
        'La Nani Cafe': 0,
        'Setenta Grados': 0,
        'La Sureña': 0
    }

    # Iterar sobre los datos del diccionario original y actualizar los montos
    for unidad in Capital:
        nombre_unidad = unidad['nombreUnidadDeNegocio']
        capital_prestado = unidad['TotalCapitalPrestado']
        unidades_negocio_capital[nombre_unidad] = capital_prestado

    # Crear la lista de resultados final con todas las unidades de negocio
    resultado_capital = []
    for nombre_unidad, capital_prestado in unidades_negocio_capital.items():
        resultado_capital.append({
            'nombreUnidadDeNegocio': nombre_unidad,
            'capital_prestado': capital_prestado
        })

    nombreUnidadDeNegocio = [unidad['nombreUnidadDeNegocio'] for unidad in resultado_capital]
    TotalCapitalPrestado = [str(unidad['capital_prestado']) for unidad in resultado_capital]

    # Interes de Ganancia de la quincena por Unidad de Negocio 
    FechaSinformato =  date.today()
    Fecha = FechaSinformato.strftime("%Y-%m-%d")

    query = "SELECT * FROM interesporunidaddenegocio(%s);"
    db.execute(query,[Fecha,])
    diccionario = crear_diccionario(db)
    monto_cuota = calcular_interes_cuota(diccionario)

    # Crear un diccionario con todas las unidades de negocio y montos iniciales en 0
    unidades_negocio = {
        # 'Mi Ranchito'
        'Mi viejo Ranchito': 0,
        'El Zocalo': 0,
        'La Nani Cafe': 0,
        'Setenta Grados': 0,
        'La Sureña': 0
    }

    # Iterar sobre los datos del diccionario original y actualizar los montos
    for i, dato in enumerate(diccionario):
        nombre_unidad = dato['nombreUnidadDeNegocio']
        monto_pago = monto_cuota[i] if i < len(monto_cuota) else 0  # Obtener el monto de pago correspondiente, o 0 si no hay
        unidades_negocio[nombre_unidad] = unidades_negocio.get(nombre_unidad, 0) + monto_pago

    # Crear la lista de resultados final con todas las unidades de negocio
    resultado = []
    for nombre_unidad, monto_pago in unidades_negocio.items():
        resultado.append({
            'nombreUnidadDeNegocio': nombre_unidad,
            'monto_pago': monto_pago
        })

    nombreUnidadDeNegocioInteres = [unidad['nombreUnidadDeNegocio'] for unidad in resultado]
    TotalInteres = [str(unidad['monto_pago']) for unidad in resultado]

    # Cerrado de la conexion 
    db.close()

    # Carga de las notificaciones
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    return render_template('dashboard.html',notificacionesIndex=notificacionesIndex,rows=rows,
        Capital = json.dumps(TotalCapitalPrestado),
        Nombres = json.dumps(nombreUnidadDeNegocio),
        NombresUnidades = json.dumps(nombres),
        numerocolaboradores = json.dumps(Numerocolaboradores),
        nombreUnidadDeNegocioInteres = json.dumps(nombreUnidadDeNegocioInteres),
        TotalInteres = json.dumps(TotalInteres)
                            )

@app.route("/logout", methods = ['GET', 'POST'])
def logout():
    # cerramos sesion 
    session.clear()
    # redireccionamos al login 
    return redirect("/")

# ruta para verificar si la contrasena del colaboorador ha sido cambiada al menos una vez como medida de seguridad
@app.route('/ocultar_modal')
def ocultar_modal():
    session.pop('primera_contrasena', None)
    return redirect(url_for('index'))

@app.route("/prestamo_detallado/<string:CedulaColaborador>/<int:IdSolicitudesPrestamos>", methods = ['GET'])
def prestamo_detallado(CedulaColaborador,IdSolicitudesPrestamos):
    
    # Conexion con la Bd
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    
    if request.method =="GET":
        
        query = "SELECT * FROM infodetalleprestamocol(%s,%s);"
        db.execute(query,(IdSolicitudesPrestamos,CedulaColaborador))
        rows = crear_diccionario(db)

        # Verificar si existe un prestamo activo
        if rows == []:
            error = 'SINPRESTAMO'
            return render_template('Error.html',error=error,notificacionesIndex=notificacionesIndex)
        
        else:

            query = "SELECT IdColaborador FROM Colaboradores WHERE CedulaColaborador=%s;"
            db.execute(query,(CedulaColaborador,))
            id_colaborador = db.fetchone()[0]
            
            # coste total
            total = rows[0]['Capital'] + (rows[0]['Capital'] * rows[0]['Intereses'] * rows[0]['Cuotas'])
            
            # buscar las fechas de pago segun el prestamo
            query = "SELECT FechaDePago FROM RegistroPagos WHERE IdPrestamo=%s;"
            db.execute(query,(rows[0]['IdPrestamo'],))
            fechas_pago = db.fetchall()

            #retorno de la demas informacion sobre las cuotas
            query = "SELECT * FROM mostrarregistropagocolaborador(%s,%s)"
            db.execute(query,(IdSolicitudesPrestamos,CedulaColaborador))
            tabla = crear_diccionario(db)

            # cuotas pendientes
            #utilizamos el siguiete formato para procedimiento que utilizan out como parametro de salida
            db.execute("SELECT obtenerpagosdeducidosporidcolaborador(%s);", (id_colaborador,))
            cuotas_deducidas = db.fetchone()[0] 

            #funcion para calcular los pagos del prestamo 
            datos = calcular_pagos(tabla,fechas_pago,cuotas_deducidas)
            
            # Modificar cada fecha en la lista de diccionarios
            for dic in datos:
                # Convertir la cadena de fecha a un objeto datetime
                fecha_obj = datetime.strptime(dic['Fecha'], "%Y-%m-%d")
                # Convertir el objeto datetime a la cadena en formato dd-mm-aaaa
                dic['Fecha'] = fecha_obj.strftime("%d-%m-%Y")

            # Cerrado de la conexion 
            db.close()
            return render_template('prestamo_detallado.html',rows=rows, datos=datos,total=total,notificacionesIndex=notificacionesIndex)

@app.route("/prestamo_activo_colaborador/<string:CedulaColaborador>", methods = ['GET'])
def prestamo_activo_colaborador(CedulaColaborador):
    
    db = mysql.connection.cursor()
    # notificaciones 
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        
        query = "SELECT IdColaborador FROM Colaboradores WHERE CedulaColaborador=%s;"
        db.execute(query,(CedulaColaborador,))
        id_colaborador = db.fetchall()[0][0]
        
        try:
            db.execute("SELECT * FROM obtenerestadoprestamomasreciente(%s);",(id_colaborador,))
            resultados  = db.fetchall()
            estado_prestamo = resultados[0][0]
            id_solicitud = resultados[0][1]

            if estado_prestamo == 'C':
                error = "SINPRESTAMO"
                return render_template('error.html',error=error,notificacionesIndex=notificacionesIndex )
            else:
                return redirect(url_for('prestamo_detallado', CedulaColaborador=CedulaColaborador, IdSolicitudesPrestamos=id_solicitud))
        except Exception as ex:
            error = "SINPRESTAMO"
            return render_template('error.html',error=error,notificacionesIndex=notificacionesIndex )
    else:
        return render_template('error.html')

# ruta administrador        
@app.route('/prestamos_activos',methods=['GET'])
def prestamos_activos():
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":
        
        id_sucursal = session["id_sucursal_admin"]
        query = "SELECT * FROM prestamosactivosporsucursal(%s)"
        db.execute(query,(id_sucursal,))
        rows = crear_diccionario(db)
        
        db.close()
        return render_template('prestamos_activos.html',rows=rows,notificacionesIndex=notificacionesIndex)

@app.route("/prestamos_cancelados", methods = ['GET'])
def prestamos_cancelados():
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":
        
        id_sucursal = session["id_sucursal_admin"]
        query = "SELECT * FROM prestamoscanceladosporsucursal(%s)"
        db.execute(query,(id_sucursal,))
        rows = crear_diccionario(db)
        
        db.close()
        return render_template('prestamos_cancelados.html',rows=rows,notificacionesIndex=notificacionesIndex)

# rutas exclusivas gerente
@app.route("/prestamos_activos_gerente",methods=['GET'])
def prestamos_activos_gerente():

    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    db = mysql.connection.cursor()
    
    if request.method == 'GET':
        db.execute("SELECT * FROM prestamosactivostodaslassucursales();")
        rows = crear_diccionario(db)
        db.close()
        return render_template('prestamos_activos.html',rows=rows,notificacionesIndex=notificacionesIndex)

@app.route("/prestamos_activos_por_sucursal/<int:IdSucursal>",methods=['GET'])
def prestamos_activos_por_sucursal(IdSucursal):
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":
        
        query = "SELECT * FROM prestamosactivosporsucursal(%s)"
        db.execute(query,(IdSucursal,))
        rows = crear_diccionario(db)
        db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s;",(IdSucursal,))
        resultados_sucursal = crear_diccionario(db)
        sucursal = resultados_sucursal[0]['nombreDeSucursal'] + " " + resultados_sucursal[0]['direccionSucursal']
        db.close()
        return render_template('prestamos_activos.html',rows=rows,notificacionesIndex=notificacionesIndex, sucursal=sucursal)

@app.route("/prestamos_cancelados_gerente",methods=['GET'])
def prestamos_cancelados_gerente():

    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    db = mysql.connection.cursor()

    if request.method == 'GET':
        db.execute("SELECT * FROM prestamoscanceladostodaslassucursales();")
        rows = crear_diccionario(db)
        db.close()
        return render_template('prestamos_cancelados.html',rows=rows,notificacionesIndex=notificacionesIndex)  

@app.route("/prestamos_cancelados_por_sucursal/<int:IdSucursal>",methods=['GET'])
def prestamos_cancelados_por_sucursal(IdSucursal):
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":
        
        query = "SELECT * FROM prestamoscanceladosporsucursal(%s)"
        db.execute(query,(IdSucursal,))
        rows = crear_diccionario(db)
        db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s;",(IdSucursal,))
        resultados_sucursal = crear_diccionario(db)
        sucursal = resultados_sucursal[0]['nombreDeSucursal'] + " " + resultados_sucursal[0]['direccionSucursal']
        db.close()
        return render_template('prestamos_cancelados.html',rows=rows,notificacionesIndex=notificacionesIndex, sucursal=sucursal)

@app.route("/solicitudes_espera_gerente", methods=['GET'])
def solicitudes_espera_gerente():
    
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    db = mysql.connection.cursor()

    if request.method == 'GET':
        db.execute("SELECT * FROM solicitudesenesperatodassucursales();")
        rows = crear_diccionario(db)
        db.close()
        return render_template('solicitudes_espera.html',rows=rows,notificacionesIndex=notificacionesIndex)  

@app.route("/solicitudes_espera_por_sucursal/<int:IdSucursal>",methods=['GET'])
def solicitudes_espera_por_sucursal(IdSucursal):
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        db.execute("SELECT * FROM solicitudesesperaporsucursal(%s);",(IdSucursal,))
        rows = crear_diccionario(db)
        db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s;",(IdSucursal,))
        resultados_sucursal = crear_diccionario(db)
        sucursal = resultados_sucursal[0]['nombreDeSucursal'] + " " + resultados_sucursal[0]['direccionSucursal']
        db.close()
        return render_template('solicitudes_espera.html',rows=rows,notificacionesIndex=notificacionesIndex, sucursal=sucursal)

@app.route("/solicitudes_aceptadas_gerente",methods=['GET'])
def solicitudes_aceptadas_gerente():

    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        db.execute("SELECT * FROM solicitudesaceptadastodassucursales();")
        rows = crear_diccionario(db)
        db.close()
        return render_template('solicitud_aceptada.html',rows=rows,notificacionesIndex=notificacionesIndex)  

@app.route("/solicitudes_aceptadas_por_sucursal/<int:IdSucursal>",methods=['GET'])
def solicitudes_aceptadas_por_sucursal(IdSucursal):
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        db.execute("SELECT * FROM solicitudesaceptadasporsucursal(%s);",(IdSucursal,))
        rows = crear_diccionario(db)
        db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s;",(IdSucursal,))
        resultados_sucursal = crear_diccionario(db)
        sucursal = resultados_sucursal[0]['nombreDeSucursal'] + " " + resultados_sucursal[0]['direccionSucursal']
        db.close()
        return render_template('solicitud_aceptada.html',rows=rows,notificacionesIndex=notificacionesIndex, sucursal=sucursal)

@app.route("/solicitudes_denegadas_gerente",methods=['GET'])
def solicitudes_denegadas_gerente():
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        db.execute("SELECT * FROM solicitudesdenegadastodassucursales();")
        rows = crear_diccionario(db)
        db.close()
        return render_template('solicitud_denegada.html',rows=rows,notificacionesIndex=notificacionesIndex)  

@app.route("/solicitudes_denegadas_por_sucursal/<int:IdSucursal>",methods=['GET'])
def solicitudes_denegadas_por_sucursal(IdSucursal):
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        db.execute("SELECT * FROM solicitudesdenegadasporsucursal(%s);",(IdSucursal,))
        rows = crear_diccionario(db)
        db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s;",(IdSucursal,))
        resultados_sucursal = crear_diccionario(db)
        sucursal = resultados_sucursal[0]['nombreDeSucursal'] + " " + resultados_sucursal[0]['direccionSucursal']
        db.close()
        return render_template('solicitud_denegada.html',rows=rows,notificacionesIndex=notificacionesIndex, sucursal=sucursal)

@app.route("/agregar_administrador",methods=['GET','POST'])
def agregar_administrador():
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    db.execute("""
        SELECT s.idsucursal AS "IdSucursal",
               s.nombredesucursal AS "nombreDeSucursal",
               s.direccionsucursal AS "direccionSucursal"
        FROM sucursales s
        WHERE NOT EXISTS (
            SELECT 1 FROM administrador a
            WHERE a.idsucursal = s.idsucursal
              AND a.estadoadministrador = '1'
              AND a.cedulaadministrador <> '000-000000-0000A'
        )
        ORDER BY s.idsucursal;
    """)
    sucursales = crear_diccionario(db)

    if request.method == 'GET':
    
        return render_template('agregar_admin.html',notificacionesIndex=notificacionesIndex,sucursales=sucursales)
    
    elif request.method == 'POST':
        
        # obtener datos del formulario
        CedulaAdministrador = request.form.get('CedulaAdministradorOutput')
        NumeroTelefonoAdministrador = request.form.get('NumeroTelefonoAdministradorOutput')
        CorreoAdministrador = request.form.get('CorreoAdministradorOutput').strip().lower()
        IdSucursal = request.form.get('IdSucursal')
        values = (CedulaAdministrador,NumeroTelefonoAdministrador,CorreoAdministrador,IdSucursal)

        # obtener todos los datos sobre los Administradores en la base de datos
        query = "SELECT CedulaAdministrador,CorreoAdministrador,NumeroTelefonoAdministrador,IdSucursal FROM Administrador WHERE EstadoAdministrador=%s AND CedulaAdministrador !=%s;"
        db.execute(query,('1','000-000000-0000A'))
        values2 = db.fetchall()
        
        #usamos listas para almacenar las cedulas,correo y numeros telefonicos ya almacenados
        cedulas = []
        correos = []
        numeros = []
        id_sucursal = []

        for value in values2:
            cedulas.append(value[0])
            correos.append(value[1])
            numeros.append(value[2])
            id_sucursal.append(str(value[3]))

        result="ERROR"    
        result = validar_insersion_admin(values,cedulas,numeros,correos,id_sucursal)

        if result == "EMAIL":
            return render_template('agregar_admin.html', error="Ya existe un administrador asociado con este correo",notificacionesIndex=notificacionesIndex,sucursales=sucursales)
        elif result == "CEDULA":
            return render_template('agregar_admin.html', error='Ya existe un administrador asociado a este número de cédula',notificacionesIndex=notificacionesIndex,sucursales=sucursales)
        elif result == "NUMERO":
            return render_template('agregar_admin.html', error='Ya existe un administrador asociado a este número telefónico',notificacionesIndex=notificacionesIndex,sucursales=sucursales)
        elif result == "ID":
            return render_template('agregar_admin.html', error='Ya existe un administrador asociado en esta sucursal',notificacionesIndex=notificacionesIndex,sucursales=sucursales)
        elif result == "ERROR":
            return render_template('agregar_admin.html', error='Todos los campos son obligatorios.',notificacionesIndex=notificacionesIndex,sucursales=sucursales)
        else:
            NombresAdministrador = request.form.get('NombresAdministradorOutput').strip().upper()
            ApellidosAdministrador = request.form.get('ApellidosAdministradorOutput').strip().upper()
            EstadoAdministrador = '1'
            #crear contraseña colaborador
            Contrasenia = crear_contrasenia_colaborador(NombresAdministrador,ApellidosAdministrador)

            #crear usuario
            db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal=%s;",(IdSucursal,))        
            datos_sucursal = crear_diccionario(db)
            Usuario = datos_sucursal[0]['nombreDeSucursal']+datos_sucursal[0]['direccionSucursal']
            Usuario = Usuario.replace(" ","")
            
            query = "CALL insertaradministrador(%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            values = (CedulaAdministrador,NombresAdministrador,ApellidosAdministrador,CorreoAdministrador,
                        NumeroTelefonoAdministrador,Usuario,contexto.hash(Contrasenia),EstadoAdministrador,IdSucursal)
            
            # Print para tener acceso al usuario recien creado 
            print(Usuario,Contrasenia)
            db.execute(query,values)
            mysql.connection.commit()
            db.close()

            # Enviar credenciales por correo (sin poner la contraseña en la URL)
            send_mail_google(
                CorreoAdministrador,
                NombresAdministrador + ' ' + ApellidosAdministrador,
                Usuario,
                Contrasenia,
            )

            return redirect(url_for('dashboard'))

@app.route('/editar_administrador', methods=['GET'])
def editar_administrador():
    
    # Conexión con la BD
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":
        # Obtener administradores activos
        db.execute("""
            SELECT idadministrador AS "IdAdministrador",
                   apellidosadministrador AS "ApellidosAdministrador",
                   nombresadministrador AS "NombresAdministrador",
                   cedulaadministrador AS "CedulaAdministrador",
                   idsucursal AS "IdSucursal"
            FROM administrador
            WHERE estadoadministrador = %s;
        """, ('1',))
        rows = crear_diccionario(db)

        # Obtener sucursales
        db.execute("""
            SELECT idsucursal AS "IdSucursal",
                   nombredesucursal AS \"nombreDeSucursal\",
                   direccionsucursal AS \"direccionSucursal\"
            FROM sucursales
            ORDER BY idsucursal;
        """)
        sucursales = crear_diccionario(db)

        # Cerrado de la conexión
        db.close()
        return render_template('editar_admin.html', rows=rows, notificacionesIndex=notificacionesIndex, sucursales=sucursales)

@app.route('/editar_administrador_detalle/<int:IdAdministrador>',methods=['GET','POST'])
def editar_administrador_detalle(IdAdministrador):
    
    # Conexion BD 
    db = mysql.connection.cursor()   
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    
    db.execute("""
        SELECT idadministrador AS "IdAdministrador",
               cedulaadministrador AS "CedulaAdministrador",
               nombresadministrador AS "NombresAdministrador",
               apellidosadministrador AS "ApellidosAdministrador",
               correoadministrador AS "CorreoAdministrador",
               numerotelefonoadministrador AS "NumeroTelefonoAdministrador",
               idsucursal AS "IdSucursal"
        FROM administrador
        WHERE idadministrador = %s;
    """, (IdAdministrador,))
    rows = crear_diccionario(db)

    query = "select nombredesucursal,direccionsucursal from sucursales where idsucursal=%s"
    db.execute(query,(rows[0]['IdSucursal'],))
    
    datos_sucursal = db.fetchall()
    nombre_sucursal = datos_sucursal[0][0]
    direccion_sucursal = datos_sucursal[0][1]

    if request.method == "GET":

        return render_template('editar_admin_detalle.html',rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
    
    elif request.method == "POST":
        
        CedulaAdministrador = request.form.get('CedulaAdministrador')
        CorreoAdministrador = request.form.get('CorreoAdministrador').strip().lower()
        NumeroTelefonoAdministrador = request.form.get('NumeroTelefonoAdministrador')
        IdSucursal = request.form.get('IdSucursal')

        values = (CedulaAdministrador,NumeroTelefonoAdministrador,CorreoAdministrador,IdSucursal)

        # obtener todos los datos sobre los colaboradores en la base de datos
        query = "SELECT CedulaAdministrador,CorreoAdministrador,NumeroTelefonoAdministrador,IdSucursal FROM Administrador WHERE EstadoAdministrador=%s AND CedulaAdministrador !=%s AND IdAdministrador!=%s;"
        db.execute(query,('1','000-000000-0000A',rows[0]['IdAdministrador']))
        values2 = db.fetchall()

        #usamos listas para almacenar las cedulas,correo y numeros telefonicos ya almacenados
        cedulas = []
        correos = []
        numeros = []
        id_sucursal = []

        for value in values2:
            cedulas.append(value[0])
            correos.append(value[1])
            numeros.append(value[2])
            id_sucursal.append(str(value[3]))

        result="ERROR"    
        result = validar_insersion_admin(values,cedulas,numeros,correos,id_sucursal)

        if result == "EMAIL":
            return render_template('editar_admin_detalle.html', error="Ya existe un administrador asociado con este correo",rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "CEDULA":
            return render_template('editar_admin_detalle.html', error='Ya existe un administrador asociado a este número de cédula',rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "NUMERO":
            return render_template('editar_admin_detalle.html', error='Ya existe un administrador asociado a este número telefónico',rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "ID":
            return render_template('editar_admin_detalle.html', error='Ya existe un administrador asociado en esta sucursal',rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "ERROR":
            return render_template('editar_admin_detalle.html', error='Todos los campos son obligatorios.',rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        else:
            NombresAdministrador = request.form.get('NombresAdministrador').strip().upper()
            ApellidosAdministrador = request.form.get('ApellidosAdministrador').strip().upper()
            query = "CALL modificaradministrador(%s,%s,%s,%s,%s,%s,%s);"
            values = (IdAdministrador,CedulaAdministrador,NombresAdministrador,ApellidosAdministrador,
                        CorreoAdministrador,NumeroTelefonoAdministrador,IdSucursal)
            
            db.execute(query,values)
            mysql.connection.commit()
            db.close()

            return redirect(url_for('dashboard'))

@app.route('/despedir_admin',methods=['GET'])
def despedir_admin():

    # Conexion de a  la  BD 
    db = mysql.connection.cursor()   
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        
        # Obtener administradores
        db.execute("""
            SELECT idadministrador AS "IdAdministrador",
                   cedulaadministrador AS "CedulaAdministrador",
                   nombresadministrador AS "NombresAdministrador",
                   apellidosadministrador AS "ApellidosAdministrador",
                   estadoadministrador AS "EstadoAdministrador",
                   idsucursal AS "IdSucursal"
            FROM administrador;
        """)
        rows = crear_diccionario(db)

        # Obtener sucursales
        db.execute("""
            SELECT idsucursal AS "IdSucursal",
                   nombredesucursal AS \"nombreDeSucursal\",
                   direccionsucursal AS \"direccionSucursal\"
            FROM sucursales
            ORDER BY idsucursal;
        """)
        sucursales = crear_diccionario(db)

        db.close()

        return render_template('despedir_admin.html',rows=rows,notificacionesIndex=notificacionesIndex,sucursales=sucursales)

@app.route('/despedir_admin_parametro/<int:IdAdministrador>',methods=['GET','POST'])
def despedir_admin_parametro(IdAdministrador):
    
    db = mysql.connection.cursor()  
    
    db.execute("CALL cambiarestadoadministrador(%s);",(IdAdministrador,))
    mysql.connection.commit()
    db.close()
    return redirect('/despedir_admin')
    
@app.route('/ver_cheque',methods=['GET'])
def ver_cheque():
    
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)
    db = mysql.connection.cursor()

    #fecha actual
    fecha_actual = datetime.now()
    fecha_actual = fecha_actual.date()

    if request.method == 'GET':
        
        db.execute("SELECT * FROM obtenerchequesporgenerartodaslassucursales(%s);",(fecha_actual,))
        diccionario = crear_diccionario(db)
        nombre_sucursal = []
        direccion_sucursal = []
        i = 0

        for datos in diccionario:
            db.execute('SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal=%s;',(datos['IdSucursal'],))
            datos_sucursal = crear_diccionario(db)
            nombre_sucursal.append(datos_sucursal[i]['nombreDeSucursal'])
            direccion_sucursal.append(datos_sucursal[i]['direccionSucursal'])

            if len(datos) < i:
                i += 1

        return render_template('generar_cheques.html',notificacionesIndex=notificacionesIndex,diccionario=diccionario,
                                nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal)

# fin rutas exclusivas gerente

@app.route("/solicitudes_espera", methods = ['GET'])
def solicitudes_espera():
    
    # Conexion de BD 
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        
        id_sucursal = session["id_sucursal_admin"]
        query = "SELECT * FROM solicitudesesperaporsucursal(%s);"
        db.execute(query,(id_sucursal,))
        rows = crear_diccionario(db)
        
        db.close()
        return render_template('solicitudes_espera.html',rows=rows,notificacionesIndex=notificacionesIndex)

@app.route("/solicitud_aceptada", methods=['GET'])
def solicitud_aceptada():
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        
        id_sucursal = session["id_sucursal_admin"]
        query = "SELECT * FROM solicitudesaceptadasporsucursal(%s);"
        db.execute(query,(id_sucursal,))
        rows = crear_diccionario(db)
        return render_template('solicitud_aceptada.html', rows=rows,notificacionesIndex=notificacionesIndex)
    
@app.route("/solicitud_denegada", methods=['GET'])
def solicitud_denegada():
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        
        id_sucursal = session["id_sucursal_admin"]
        query = "SELECT * FROM solicitudesdenegadasporsucursal(%s);"
        db.execute(query,(id_sucursal,))
        rows = crear_diccionario(db)
        return render_template('solicitud_denegada.html', rows=rows,notificacionesIndex=notificacionesIndex)

@app.route('/agregar_colaborador',methods=['GET', 'POST'])
def agregar_colaborador():

    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    id_sucursal_admin = session.get('id_sucursal_admin')
    # Conexion con la Bd
    db = mysql.connection.cursor()

    query = "select nombredesucursal,direccionsucursal from sucursales where idsucursal=%s"
    db.execute(query,(id_sucursal_admin,))
    datos_sucursal = db.fetchall()
    nombre_sucursal = datos_sucursal[0][0]
    direccion_sucursal = datos_sucursal[0][1]

    if request.method == 'GET':
        
        return render_template('agregar_colaborador.html',nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
    
    elif request.method == 'POST':
        
        CedulaColaborador = request.form.get('CedulaColaboradorOutput')
        NumeroTelefonoColaborador = request.form.get('NumeroTelefonoColaboradorOutput')
        CorreoColaborador = request.form.get('CorreoColaboradorOutput').strip().lower()
        values = (CedulaColaborador,NumeroTelefonoColaborador,CorreoColaborador)

        # obtener todos los datos sobre los colaboradores en la base de datos
        query = "SELECT CedulaColaborador,CorreoColaborador,NumeroTelefonoColaborador FROM Colaboradores;"
        db.execute(query)
        values2 = db.fetchall()

        #usamos listas para almacenar las cedulas,correo y numeros telefonicos ya almacenados
        cedulas = []
        correos = []
        numeros = []

        for value in values2:

            cedulas.append(value[0])
            correos.append(value[1])
            numeros.append(value[2])

        result=''     
        result = validar_insersion_colaborador(values,cedulas,numeros,correos)

        if result == "EMAIL":
            return render_template('agregar_colaborador.html', error="Ya existe un colaborador asociado con este correo", nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "CEDULA":
            return render_template('agregar_colaborador.html', error='Ya existe un colaborador asociado a este número de cédula',nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "NUMERO":
            return render_template('agregar_colaborador.html', error='Ya existe un colaborador asociado a este número telefónico',nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        elif result == "ERROR":
            return render_template('agregar_colaborador.html', error='Todos los campos son obligatorios.',nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
        else:
            FechaContratacion = request.form.get('FechaContratacion')
            NombresColaborador = request.form.get('NombresColaboradorOutput').strip().upper()
            ApellidosColaborador = request.form.get('ApellidosColaboradorOutput').strip().upper()
            IdSucursal = id_sucursal_admin
            TipoDeContrato = request.form.get('TipoDeContrato')
            EstadoCrediticio = '0'
            EstadoColaborador = 'A'
            SalarioColaborador = request.form.get('SalarioColaboradorOutput').strip()
            salario_sin_comas = SalarioColaborador.replace(',', '')
            
            #crear contraseña colaborador
            Contrasenia = crear_contrasenia_colaborador(NombresColaborador,ApellidosColaborador)

            # Print  para tener acceso al usuario recien creado 
            print(CedulaColaborador)
            print(Contrasenia)

            query = """
                CALL insertarcolaborador(
                    %s::date, %s, %s, %s, %s::numeric, %s, %s, %s, %s, %s, %s::integer, %s
                )
            """
            values = (FechaContratacion,CedulaColaborador,NombresColaborador,ApellidosColaborador,
                    salario_sin_comas,TipoDeContrato,EstadoCrediticio,CorreoColaborador,NumeroTelefonoColaborador,
                    contexto.hash(Contrasenia),IdSucursal, EstadoColaborador)
            
            db.execute(query,values)
            mysql.connection.commit()
            db.close()

            # Enviar credenciales por correo (sin poner la contraseña en la URL)
            send_mail_google(
                CorreoColaborador,
                NombresColaborador + ' ' + ApellidosColaborador,
                CedulaColaborador,
                Contrasenia,
            )

            return redirect(url_for('index'))

# Ruta opcional / legacy para reenvio manual (evita usarla como camino principal:
# la contraseña viaja en la URL)
@app.route('/enviar_correo/<string:CorreoColaborador>/<string:NombresColaborador>/<string:ApellidosColaborador>/<string:CedulaColaborador>/<string:Contrasenia>')
def enviar_correo(CorreoColaborador,NombresColaborador,ApellidosColaborador,CedulaColaborador,Contrasenia):
    send_mail_google(CorreoColaborador,NombresColaborador+' '+ApellidosColaborador,CedulaColaborador,Contrasenia)
    
    return redirect(url_for('index'))
    
@app.route('/editar_colaborador')
def editar_colaborador():
    if request.method == "GET":
        # Conexion con la Bd
        db = mysql.connection.cursor()
        # Procedimiento de almacenado Para mostrar los colaboradores por sucursal
        query = """
            SELECT idcolaborador AS "IdColaborador",
                   fechacontratacion AS "FechaContratacion",
                   cedulacolaborador AS "CedulaColaborador",
                   nombrescolaborador AS "NombresColaborador",
                   apellidoscolaborador AS "ApellidosColaborador",
                   salariocolaborador AS "SalarioColaborador",
                   tipodecontrato AS "TipoDeContrato",
                   estadocrediticio AS "EstadoCrediticio",
                   correocolaborador AS "CorreoColaborador",
                   numerotelefonocolaborador AS "NumeroTelefonoColaborador",
                   contrasenia AS "Contrasenia",
                   idsucursal AS "IdSucursal",
                   estadocolaborador AS "EstadoColaborador"
            FROM mostrarcolaboradoresporsucursal(%s)
        """
        id_administrador = session["id_administrador"]
        db.execute(query,(id_administrador,))
        rows = crear_diccionario(db)

        # Cerrado de la conexion 
        db.close()

        tiporol = session.get('type')
        notificacionesIndex = funcion_notificaciones(tiporol)
        # Pasa los datos a la plantilla HTML para ser renderizados
        return render_template('editar_colaborador.html', rows=rows,notificacionesIndex=notificacionesIndex)
    else:
        return render_template('Error.html')

@app.route("/editar_colaborador_detalle/<int:IdColaborador>", methods = ['GET', 'POST'])
def editar_colaborador_detalle(IdColaborador):
    
    db = mysql.connection.cursor()   
    
    if request.method == "GET":
        
        # Procedimiento de ALmacenado para mostrar datos por defecto de un colaborador
        query = """
            SELECT idcolaborador AS "IdColaborador",
                   fechacontratacion AS "FechaContratacion",
                   cedulacolaborador AS "CedulaColaborador",
                   nombrescolaborador AS "NombresColaborador",
                   apellidoscolaborador AS "ApellidosColaborador",
                   salariocolaborador AS "SalarioColaborador",
                   tipodecontrato AS "TipoDeContrato",
                   estadocrediticio AS "EstadoCrediticio",
                   correocolaborador AS "CorreoColaborador",
                   numerotelefonocolaborador AS "NumeroTelefonoColaborador",
                   contrasenia AS "Contrasenia",
                   idsucursal AS "IdSucursal",
                   estadocolaborador AS "EstadoColaborador"
            FROM mostraruncolaborador(%s)
        """
        db.execute(query,(IdColaborador,))
        # Creacion del diccionario 
        rows = crear_diccionario(db)

        query = "select nombredesucursal,direccionsucursal from sucursales where idsucursal=%s"
        db.execute(query,(rows[0]['IdSucursal'],))
        datos_sucursal = db.fetchall()
        nombre_sucursal = datos_sucursal[0][0]
        direccion_sucursal = datos_sucursal[0][1]

        tiporol = session.get('type')
        notificacionesIndex = funcion_notificaciones(tiporol)
        return render_template('editar_colaborador_detalle.html',rows=rows,nombre_sucursal=nombre_sucursal,direccion_sucursal=direccion_sucursal,notificacionesIndex=notificacionesIndex)
    
    elif request.method == "POST":
        
        CedulaColaborador = request.form.get('CedulaColaborador')
        NombresColaborador = request.form.get('NombresColaborador')
        ApellidosColaborador = request.form.get('ApellidosColaborador')
        SalarioColaborador = request.form.get('SalarioColaborador')
        TipoDeContrato = request.form.get('TipoDeContrato')
        CorreoColaborador = request.form.get('CorreoColaborador')
        NumeroTelefonoColaborador = request.form.get('NumeroTelefonoColaborador')

        query = "CALL modificarcolaborador(%s::integer, %s, %s, %s, %s::numeric, %s, %s, %s)"
        values = (IdColaborador,CedulaColaborador,NombresColaborador,ApellidosColaborador,SalarioColaborador,
                    TipoDeContrato,CorreoColaborador,NumeroTelefonoColaborador)
        db.execute(query,values)
        mysql.connection.commit()
        db.close()

        return redirect(url_for('editar_colaborador'))

@app.route('/eliminar_colaborador', methods = ['GET', 'POST'])
def eliminar_colaborador():

    if request.method == "GET":
        # Conexion con la Bd
        db = mysql.connection.cursor()
        # Procedimiento de almacenado Pra prestamos activos 
        query = """
            SELECT idcolaborador AS "IdColaborador",
                   fechacontratacion AS "FechaContratacion",
                   cedulacolaborador AS "CedulaColaborador",
                   nombrescolaborador AS "NombresColaborador",
                   apellidoscolaborador AS "ApellidosColaborador",
                   salariocolaborador AS "SalarioColaborador",
                   tipodecontrato AS "TipoDeContrato",
                   estadocrediticio AS "EstadoCrediticio",
                   correocolaborador AS "CorreoColaborador",
                   numerotelefonocolaborador AS "NumeroTelefonoColaborador",
                   contrasenia AS "Contrasenia",
                   idsucursal AS "IdSucursal",
                   estadocolaborador AS "EstadoColaborador"
            FROM mostrarcolaboradoresporsucursal(%s)
        """
        id_administrador = session["id_administrador"]
        db.execute(query,(id_administrador,))
        # Creacion del diccionario 
        rows = crear_diccionario(db)

        # Cerrado de la conexion 
        db.close()
        tiporol = session.get('type')
        notificacionesIndex = funcion_notificaciones(tiporol)
        return render_template('eliminar_colaborador.html', rows=rows,notificacionesIndex=notificacionesIndex)
    else:
        return render_template('eliminar_colaborador.html')

@app.route("/eliminarcolaborador/<int:IdColaborador>", methods = ['GET', 'POST'])
def eliminarcolaborador(IdColaborador):

    #query para eliminar el colaborador 
    db = mysql.connection.cursor()  
    query = "CALL cambiarestadocolaborador(%s)"   
    db.execute(query,(IdColaborador,))
    mysql.connection.commit()
    db.close()
    return redirect('/eliminar_colaborador')

@app.route('/opciones_inactividad_colaborador/<string:CedulaColaborador>',methods = ['GET','POST'])
def opciones_inactividad_colaborador(CedulaColaborador):
    
    db = mysql.connection.cursor()
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == 'GET':
        
        query = "SELECT IdColaborador,NombresColaborador,ApellidosColaborador FROM Colaboradores WHERE CedulaColaborador=%s;"
        db.execute(query,(CedulaColaborador,))
        datosColaborador = crear_diccionario(db)

        db.execute("SELECT * FROM obtenercapitalinteresyplazopago(%s);",(datosColaborador[0]['IdColaborador'],))
        datosPrestamo = db.fetchall()
        
        id_prestamo = datosPrestamo[0][0]
        id_solicitud = datosPrestamo[0][1]
        capital = datosPrestamo[0][2]
        intereses = datosPrestamo[0][3]
        plazo_de_pago = datosPrestamo[0][4]
        
        #utilizamos el siguiete formato para procedimiento que utilizan out como parametro de salida
        db.execute("SELECT obtenerpagospendientesporidcolaborador(%s);",(datosColaborador[0]['IdColaborador'],))
        cuotas_pendientes = db.fetchone()[0] 
        
        if cuotas_pendientes == plazo_de_pago*2:
            monto_deducido = capital
        else:
            #calcular el monto que se va a deducir sin intereses
            pago_total = capital + (capital* intereses * (plazo_de_pago*2))
            pago_total_por_cuota = pago_total / (plazo_de_pago*2)
            pago_total_pendiente_con_intereses = pago_total_por_cuota * cuotas_pendientes
            capital_cuota = capital / (plazo_de_pago*2)
            capital_pendiente = capital_cuota * cuotas_pendientes
            monto_deducido = round(pago_total_pendiente_con_intereses - capital_pendiente,2)

        return render_template('opciones_inactividad_colaborador.html',datosColaborador=datosColaborador,CedulaColaborador=CedulaColaborador,
                                cuotas=cuotas_pendientes, monto_deducido=monto_deducido,id_prestamo=id_prestamo,
                                id_solicitud=id_solicitud,notificacionesIndex=notificacionesIndex)

@app.route('/deducir_prestamo/<string:CedulaColaborador>/<int:IdSolicitud>/<int:IdPrestamo>')
def deducir_prestamo(CedulaColaborador:str,IdSolicitud:int,IdPrestamo:int):
    
    fecha_actual = datetime.now()

    db = mysql.connection.cursor()
    # actualizar registros de pago a Deducidos con fecha del dia de la deduccion
    query = "UPDATE RegistroPagos SET FechaDePago = %s, EstadoCuota='D' WHERE IdPrestamo = %s AND EstadoCuota='P';"
    db.execute(query,(fecha_actual,IdPrestamo,))
    mysql.connection.commit()
    
    # actualizar el estado de prestamo a cancelado
    db.execute("UPDATE Prestamos SET EstadoPrestamo ='C' WHERE IdPrestamo = %s;",(IdPrestamo,))
    mysql.connection.commit()
    # actualizar el estado crediticio del colaborador
    db.execute("UPDATE Colaboradores SET EstadoCrediticio = '0',EstadoColaborador='D' WHERE CedulaColaborador = %s;",(CedulaColaborador,))    
    mysql.connection.commit()
    
    # actualizar el estado del colaborador: Pediente 
    return redirect(url_for('index'))

@app.route('/detalle_solicitud/<int:IdColaborador>/<int:IdSolicitudesPrestamos>', methods = ['GET', 'POST'])
def detalle_solicitud(IdColaborador,IdSolicitudesPrestamos):
    
    db = mysql.connection.cursor()   
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":
        
        # Procedimiento de ALmacenado para mostrar datos por defecto de un colaborador
        query = """
            SELECT idcolaborador AS "IdColaborador",
                   fechacontratacion AS "FechaContratacion",
                   cedulacolaborador AS "CedulaColaborador",
                   nombrescolaborador AS "NombresColaborador",
                   apellidoscolaborador AS "ApellidosColaborador",
                   salariocolaborador AS "SalarioColaborador",
                   tipodecontrato AS "TipoDeContrato",
                   estadocrediticio AS "EstadoCrediticio",
                   correocolaborador AS "CorreoColaborador",
                   numerotelefonocolaborador AS "NumeroTelefonoColaborador",
                   contrasenia AS "Contrasenia",
                   idsucursal AS "IdSucursal",
                   estadocolaborador AS "EstadoColaborador"
            FROM mostraruncolaborador(%s)
        """
        db.execute(query,(IdColaborador,))
        rows = crear_diccionario(db)
        
        # calcular el monto acumulado del colborador
        monto = calcular_monto_acumulado_hasta_fecha_actual(rows[0]['FechaContratacion'],rows[0]['SalarioColaborador'])
        
        #query para mostrar la informacion de la solicitud de un colaborador
        query = """
            SELECT idsolicitudesprestamos AS "IdSolicitudesPrestamos",
                   fechadesolicitud AS "FechaDeSolicitud",
                   montosolicitado AS "MontoSolicitado",
                   plazodepago AS "PlazoDePago",
                   motivoprestamo AS "MotivoPrestamo"
            FROM solicitudesprestamos
            WHERE idcolaborador = %s AND idsolicitudesprestamos = %s
        """
        db.execute(query,(IdColaborador,IdSolicitudesPrestamos))
        rowsSolicitud = crear_diccionario(db)
        
        #Obtener los datos de la sucursal para mostrar el el campo de tipo texto no editable
        query = "select nombredesucursal,direccionsucursal from sucursales where idsucursal=%s"
        db.execute(query,(rows[0]['IdSucursal'],))
        datos_sucursal = db.fetchall()
        nombre_sucursal = datos_sucursal[0][0]
        direccion_sucursal = datos_sucursal[0][1]

        return render_template('detalle_solicitud.html',rows=rows, 
                                rowsSolicitud=rowsSolicitud,                       
                                nombre_sucursal=nombre_sucursal,
                                direccion_sucursal=direccion_sucursal,monto=monto,notificacionesIndex=notificacionesIndex)
    
    else:
        # recuperamos los de los inputs escondidos   
        IdSolicitudesPrestamos = request.form.get('idSolicitudesPresamos')
        IdColaborador = request.form.get('idColaborador')
        # recuperamos datos del formulario
        MontoAprobado = Decimal(request.form.get('MontoAprobadoOutput').replace(',', '.'))
        PlazoDePagoAprobado = request.form.get('PlazoDePagoAprobadoOutput')
        Cuotas = int(PlazoDePagoAprobado) * 2 
        FechaDeAprobacion = datetime.now()
        FechaDeAprobacion = FechaDeAprobacion.date()

        db.execute(
            "SELECT fechacontratacion, salariocolaborador FROM colaboradores WHERE idcolaborador = %s",
            (IdColaborador,),
        )
        fecha_contratacion, salario = db.fetchone()
        monto_maximo = calcular_monto_acumulado_hasta_fecha_actual(fecha_contratacion, salario)
        if MontoAprobado > monto_maximo:
            flash(f'El monto aprobado no puede ser mayor que el monto máximo calculado: C${monto_maximo}')
            return redirect(url_for(
                'detalle_solicitud',
                IdColaborador=IdColaborador,
                IdSolicitudesPrestamos=IdSolicitudesPrestamos,
            ))

        if session['cedula_administrador'] == "000-000000-0000A":
            interes = Decimal(request.form.get('InteresAprobado'))
            interes = interes/100
        else:
            interes = calcular_interes(MontoAprobado)
        
        id_admin = session["id_administrador"]
        
        db.execute(
            "SELECT idprestamo FROM prestamos WHERE idsolicitudesprestamos = %s",
            (IdSolicitudesPrestamos,),
        )
        prestamo_existente = db.fetchone()

        if prestamo_existente is None:
            query = """INSERT INTO prestamos (fechadeaprobacion, capital, intereses, cuotas, plazodepago_meses, estadoprestamo, idsolicitudesprestamos, idadministrador)
                    VALUES
                    (%s, %s,%s,%s,%s, %s,%s,%s)"""
            db.execute(query,(FechaDeAprobacion,MontoAprobado,Decimal(interes),Cuotas,PlazoDePagoAprobado,'A',IdSolicitudesPrestamos,id_admin))
            mysql.connection.commit()
            db.execute(
                "SELECT idprestamo FROM prestamos WHERE idsolicitudesprestamos = %s",
                (IdSolicitudesPrestamos,),
            )
            id_prestamo = db.fetchone()[0]
        else:
            id_prestamo = prestamo_existente[0]
        db.close()

        #actualizar la solicitud a aprobada
        db = mysql.connection.cursor()
        query = "UPDATE solicitudesprestamos SET estadosolicitud = 'A' WHERE idsolicitudesprestamos = %s;"
        db.execute(query,(IdSolicitudesPrestamos,))
        mysql.connection.commit()
        db.close()
        # actualizar el estado crediticio del colaborador
        db = mysql.connection.cursor()
        query = "UPDATE colaboradores SET estadocrediticio = '1' WHERE idcolaborador = %s;"
        db.execute(query,(IdColaborador,))
        mysql.connection.commit()
        db.close()

        #Calcular cuotas de pago solo si este prestamo aun no tiene fechas
        db = mysql.connection.cursor()
        db.execute("SELECT 1 FROM registropagos WHERE idprestamo = %s LIMIT 1", (id_prestamo,))
        if db.fetchone() is None:
            db.execute("CALL calcularfechasdepago(%s::integer);", (id_prestamo,))
            mysql.connection.commit()
        db.close()
        return redirect(url_for('solicitud_aceptada')) 

@app.route('/generar_solicitud', methods = ['GET', 'POST'])
def generar_solicitud():

    fecha_actual = datetime.now()
    fecha_mostrada = fecha_actual.strftime("%d/%m/%Y")

    id_colaborador = session["id_colaborador"]

    db = mysql.connection.cursor()

    db.execute("SELECT validarsolicitudprestamoyestado(%s)", (id_colaborador,))
    result = db.fetchone()[0]

    query = "SELECT EstadoColaborador,FechaContratacion,SalarioColaborador FROM Colaboradores WHERE IdColaborador = %s;"
    db.execute(query,(id_colaborador,))
    values = db.fetchall()

    EstadoColaborador = values[0][0]
    FechaContratacion = values[0][1]
    SalarioColaborador = values[0][2]

    liquidacion = calcular_monto_acumulado_hasta_fecha_actual(FechaContratacion,SalarioColaborador)

    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":

        return render_template('solicitud_prestamo_colaborador.html', fecha_mostrada=fecha_mostrada, result=result,
                                EstadoColaborador=EstadoColaborador,liquidacion=liquidacion,FechaContratacion=FechaContratacion,notificacionesIndex=notificacionesIndex)
    
    if request.method == "POST":
        
        MontoSolicitado = request.form.get('MontoSolicitadoOutput')
        liquidacion = request.form.get('liquidacion')

        FechaDeSolicitud = fecha_actual.strftime("%Y-%m-%d")
        PlazoDePago = request.form.get('PlazoDePagoOutput')
        MotivoDePrestamo = request.form.get('MotivoDePrestamoOutput')
        EstadoDeSolicitud = 'E'
        IdColaborador = id_colaborador

        sucursal_colaborador = session["id_sucursal_colaborador"]

        query = "SELECT idadministrador FROM administrador WHERE idsucursal=%s"
        db.execute(query,(sucursal_colaborador,))
        result = db.fetchall()
        IdAdministrador = result[0][0]
        
        query = """
            CALL insertarsolicitudprestamos(
                %s, %s::numeric, %s::integer, %s, %s, %s::integer, %s::integer
            )
        """
        values = (FechaDeSolicitud,MontoSolicitado,PlazoDePago,MotivoDePrestamo,EstadoDeSolicitud,
                IdColaborador,IdAdministrador)
        db.execute(query,values)
        mysql.connection.commit()

        db.close()

        return redirect(url_for('index'))

@app.route('/denegar_solicitud/<int:IdColaborador>', methods = ['GET', 'POST'])
def denegar_solicitud(IdColaborador):
    
    db = mysql.connection.cursor()  
    query = "UPDATE SolicitudesPrestamos SET EstadoSolicitud = 'D' WHERE IdColaborador = %s"
    db.execute(query,(IdColaborador,))
    mysql.connection.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/registro_cuotas')
def registro_cuotas():

    db = mysql.connection.cursor()

    if request.method == 'GET':
        
        id_admin = session["id_administrador"]
        query = "SELECT * FROM obtenercuotasporpagar(%s);"
        db.execute(query,(id_admin,))
        diccionario = crear_diccionario(db)
        monto_cuota = calcular_monto_cuota(diccionario)

        # creamos variables para hacer las actualizaciones automaticas
        fecha_actual = datetime.now()
        dia_actual = fecha_actual.day

        # Obtener el año y el mes actuales
        year = fecha_actual.year
        month = fecha_actual.month
        # Obtener el último día del mes actual
        ultimo_dia_mes = calendar.monthrange(year, month)[1]
        # Crear una fecha con el último día del mes actual
        ultimo_dia_fecha = datetime(year, month, ultimo_dia_mes)
        # Calcular el primer día del mes siguiente
        primer_dia_mes_siguiente = ultimo_dia_fecha + timedelta(days=1)

        if dia_actual == 16 or fecha_actual == primer_dia_mes_siguiente:
            query = "CALL actualizarestadocuotasautomatico(%s);"
            db.execute(query,(fecha_actual,))
            mysql.connection.commit()
            db.close()
            
        tiporol = session.get('type')
        notificacionesIndex = funcion_notificaciones(tiporol)
        
        return render_template('registro_cuotas.html',diccionario=diccionario,monto_cuota=monto_cuota,notificacionesIndex=notificacionesIndex)
    
@app.route('/actualizar_cuota/<int:IdRegistroPago>')
def actualizar_cuota(IdRegistroPago):
    
    db = mysql.connection.cursor()
    query = "UPDATE RegistroPagos SET EstadoCuota='C' WHERE IdRegistroPago=%s;"
    db.execute(query,(IdRegistroPago,))
    mysql.connection.commit()
    db.close()

    return redirect(url_for('registro_cuotas'))

@app.route('/historial_reportes')
def historial_reportes():
    db = mysql.connection.cursor()
    if request.method == 'GET':
        id_administrador = session["id_administrador"]
        cedula_administrador = session["cedula_administrador"]

        if cedula_administrador  == "000-000000-0000A":
            query = "SELECT * FROM historialquincenasgerente();"
            db.execute(query)
            historial = crear_diccionario(db)
        else:
            query = "SELECT * FROM historialquincenas(%s);"
            db.execute(query,[id_administrador])
            historial = crear_diccionario(db)
        
        db.close()
        tiporol = session.get('type')
        notificacionesIndex = funcion_notificaciones(tiporol)
        return render_template('historial_reportes.html',notificacionesIndex=notificacionesIndex,historial=historial)

@app.route('/solicitudes_colaborador',methods = ['GET'])
def solicitudes_colaborador():

    db = mysql.connection.cursor()

    if request.method == "GET":
        
        id_colaborador = session["id_colaborador"]
        query = "SELECT CedulaColaborador FROM Colaboradores WHERE IdColaborador = %s;"
        db.execute(query,(id_colaborador,))
        cedula = db.fetchall()[0][0]
        
        query = "SELECT * FROM historialsolicitudescolaborador(%s);"
        db.execute(query,(cedula,))

        # Creacion del diccionario 
        historial = crear_diccionario(db)

        tiporol = session.get('type')
        notificacionesIndex = funcion_notificaciones(tiporol)
        db.close()
        return render_template('solicitudes_colaborador.html',historial=historial,cedula=cedula,notificacionesIndex=notificacionesIndex)

@app.route('/ver_solcitud_colaborador/<FechaDeSolicitud>/<float:MontoSolicitado>/<int:PlazoDePago>/<EstadoSolicitud>/<cedula>/<string:MotivoPrestamo>')
def ver_solcitud_colaborador(FechaDeSolicitud,MontoSolicitado,PlazoDePago,EstadoSolicitud,cedula,MotivoPrestamo):

    # Conexion a la BD
    db = mysql.connection.cursor()
    
    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    if request.method == "GET":

        historial = {"FehaDeSolicitud":FechaDeSolicitud, "MontoSolicitado": MontoSolicitado,
                    "PlazoDePago" : PlazoDePago, "EstadoSolicitud": EstadoSolicitud,
                    "MotivoPrestamo" : MotivoPrestamo }

        FechaDeSolicitud = str(FechaDeSolicitud)
        fecha_actual = datetime.now()

        FechaDeSolicitud = datetime.strptime(FechaDeSolicitud, "%Y-%m-%d")

        diferencia = relativedelta(fecha_actual,FechaDeSolicitud)

        dias_exactos = diferencia.days
        
        query = "SELECT * FROM historialprestamoscolaborador(%s);"
        db.execute(query,(cedula,))
        historialPrestamo = db.fetchall()
        id_solicitud = None # no debe haber ningun valor de id_solicitud con 0
        
        if historialPrestamo:
            id_solicitud = historialPrestamo[0][6]
            columns = [column[0] for column in db.description]
            historialPrestamo = dict(zip(columns, historialPrestamo[0]))

            return render_template('ver_solicitud_colaborador.html',i=historial,historialPrestamo=historialPrestamo,
                                dias_exactos=dias_exactos,cedula=cedula,id_solicitud=id_solicitud,
                                notificacionesIndex=notificacionesIndex)
        else:
            return render_template('ver_solicitud_colaborador.html',i=historial,historialPrestamo=historialPrestamo,
                                dias_exactos=dias_exactos,cedula=cedula,id_solicitud=id_solicitud,
                                notificacionesIndex=notificacionesIndex)
            
@app.route('/contrasenia_colaborador', methods = ['GET','POST'])
def contrasenia_colaborador():

    db = mysql.connection.cursor()
    id_colaborador = session['id_colaborador']

    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    query = """
        SELECT idcolaborador AS "IdColaborador",
               fechacontratacion AS "FechaContratacion",
               cedulacolaborador AS "CedulaColaborador",
               nombrescolaborador AS "NombresColaborador",
               apellidoscolaborador AS "ApellidosColaborador",
               salariocolaborador AS "SalarioColaborador",
               tipodecontrato AS "TipoDeContrato",
               estadocrediticio AS "EstadoCrediticio",
               correocolaborador AS "CorreoColaborador",
               numerotelefonocolaborador AS "NumeroTelefonoColaborador",
               contrasenia AS "Contrasenia",
               idsucursal AS "IdSucursal",
               estadocolaborador AS "EstadoColaborador"
        FROM mostraruncolaborador(%s);
    """
    db.execute(query,(id_colaborador,))
    
    # Creacion del diccionario 
    result_colaborador = crear_diccionario(db)
    
    #query para encontrar el nombre y direccion de la sucursal por el id
    query = "SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s"
    sucursal_colaborador = session['id_sucursal_colaborador']
    db.execute(query,(sucursal_colaborador,))
    sucursal_colaborador = db.fetchall()
    sucursal_colaborador = sucursal_colaborador[0]

    if request.method == "GET":

        return render_template('contrasenia_colaborador.html',result_colaborador=result_colaborador,sucursal_colaborador=sucursal_colaborador,notificacionesIndex=notificacionesIndex)
    
    elif request.method=="POST":

        #variable que contrala el pop, segun los valores que se le den en los if posteriores, serán 
        #los mensajes que se mostrarán en pantalla respectivamente
        pass_pop = 0

        #se la contraseña actual del formulario
        contraseniaActualColaborador = request.form.get('actualContraseniaColaborador')

        #mandamos a llamar la contrasenia de la bd con el id del colaborador
        query = "SELECT Contrasenia FROM Colaboradores WHERE IdColaborador = %s;"
        db.execute(query,(id_colaborador,))
        #esta contraseña por defecto está encriptada
        contrasenia_encriptada = db.fetchall()
        contrasenia_encriptada = contrasenia_encriptada[0][0]

        nuevaContraseniaColaborador = request.form.get('nuevaContraseniaColaborador')
        
        #verificamos si la contraseña encriptada de la base de datos es igual a la ingresada desde 
        #el form
        if contexto.verify(contraseniaActualColaborador,contrasenia_encriptada) and nuevaContraseniaColaborador != contraseniaActualColaborador:
            
            confirmarContraseniaColaborador = request.form.get('confirmarContraseniaColaborador')
            
            #verficamos si la verificacion de contraseña es correcta
            if nuevaContraseniaColaborador == confirmarContraseniaColaborador:
                
                if len(nuevaContraseniaColaborador) < 8 or len(confirmarContraseniaColaborador) < 8: 
                    pass_pop = 2
                    return render_template('contrasenia_colaborador.html', pass_pop=pass_pop,result_colaborador=result_colaborador,
                                        sucursal_colaborador=sucursal_colaborador,notificacionesIndex=notificacionesIndex)
                else:
                    #si las contraseñas coinciden, encriptamos la contraseña para actualizar la bd
                    contrasenia_encriptada = contexto.hash(nuevaContraseniaColaborador)

                    #actualizamos la contraseña por el id de usuario, cerramos la conexión y retornamos 
                    #al login
                    query = "UPDATE Colaboradores SET Contrasenia=%s WHERE IdColaborador=%s;"
                    db.execute(query,(contrasenia_encriptada,id_colaborador))
                    mysql.connection.commit()
                    db.close()

                    session.clear()
                    return render_template('login.html')
            else:
                pass_pop = 0
                return render_template('contrasenia_colaborador.html', pass_pop=pass_pop,result_colaborador=result_colaborador,
                                        sucursal_colaborador=sucursal_colaborador,notificacionesIndex=notificacionesIndex)
        elif nuevaContraseniaColaborador == contraseniaActualColaborador:
            pass_pop = -1  
            return render_template('contrasenia_colaborador.html', pass_pop=pass_pop,result_colaborador=result_colaborador,
                                    sucursal_colaborador=sucursal_colaborador,notificacionesIndex=notificacionesIndex)     
        else:
            pass_pop = 1
            return render_template('contrasenia_colaborador.html', pass_pop=pass_pop,result_colaborador=result_colaborador,
                                    sucursal_colaborador=sucursal_colaborador,notificacionesIndex=notificacionesIndex)

@app.route('/contrasenia_admin', methods = ['GET','POST'])
def contrasenia_admin():
    
    db = mysql.connection.cursor()
    id_admin = session["id_administrador"]

    tiporol = session.get('type')
    notificacionesIndex = funcion_notificaciones(tiporol)

    query = """
        SELECT idadministrador AS "IdAdministrador",
               cedulaadministrador AS "CedulaAdministrador",
               nombresadministrador AS "NombresAdministrador",
               apellidosadministrador AS "ApellidosAdministrador",
               correoadministrador AS "CorreoAdministrador",
               numerotelefonoadministrador AS "NumeroTelefonoAdministrador",
               usuario AS "Usuario",
               contrasenia AS "Contrasenia",
               estadoadministrador AS "EstadoAdministrador",
               idsucursal AS "IdSucursal"
        FROM mostardatosadmin(%s);
    """
    db.execute(query,(id_admin,))

    # Creacion del diccionario 
    result_admin = crear_diccionario(db)

    #query para encontrar el nombre y direccion de la sucursal por el id
    query = "SELECT nombredesucursal AS \"nombreDeSucursal\", direccionsucursal AS \"direccionSucursal\" FROM Sucursales WHERE IdSucursal = %s"
    sucursal_admin = session["id_sucursal_admin"]
    db.execute(query,(sucursal_admin,))
    sucursal_admin = db.fetchall()
    sucursal_admin = sucursal_admin[0]

    if request.method == "GET":

        return render_template('contrasenia_admin.html',result_admin=result_admin,sucursal_admin=sucursal_admin, notificacionesIndex=notificacionesIndex)
    
    elif request.method=="POST":

        #variable que contrala el pop, segun los valores que se le den en los if posteriores, serán 
        #los mensajes que se mostrarán en pantalla respectivamente
        pass_pop = 0

        #se la contraseña actual del formulario
        contraseniaActualAdministrador = request.form.get('actualContraseniaAdministrador')

        #mandamos a llamar la contrasenia de la bd con el id del admin
        query = "SELECT Contrasenia FROM Administrador WHERE IdAdministrador = %s;"
        db.execute(query,(id_admin,))
        #esta contraseña por defecto está encriptada
        contrasenia_encriptada = db.fetchall()
        contrasenia_encriptada = contrasenia_encriptada[0][0]

        nuevaContraseniaAdministrador = request.form.get('nuevaContraseniaAdministrador')
        
        #verificamos si la contraseña encriptada de la base de datos es igual a la ingresada desde 
        #el form
        if contexto.verify(contraseniaActualAdministrador,contrasenia_encriptada) and nuevaContraseniaAdministrador != contraseniaActualAdministrador:
            
            confirmarContraseniaAdministrador = request.form.get('confirmarContraseniaAdministrador')
            
            #verficamos si la verificacion de contraseña es correcta
            if nuevaContraseniaAdministrador == confirmarContraseniaAdministrador:
                
                if len(nuevaContraseniaAdministrador) < 8 or len(confirmarContraseniaAdministrador) < 8: 
                    pass_pop = 2
                    return render_template('contrasenia_admin.html', pass_pop=pass_pop,result_admin=result_admin,
                                        sucursal_admin=sucursal_admin,notificacionesIndex=notificacionesIndex)           
                else:
                
                    #si las contraseñas coinciden, encriptamos la contraseña para actualizar la bd
                    contrasenia_encriptada = contexto.hash(nuevaContraseniaAdministrador)

                    #actualizamos la contraseña por el id de admin, cerramos la conexión y retornamos 
                    #al login
                    query = "UPDATE Administrador SET Contrasenia=%s WHERE IdAdministrador=%s;"
                    db.execute(query,(contrasenia_encriptada,id_admin))
                    mysql.connection.commit()
                    db.close()

                    session.clear()
                    return render_template('login.html')
            else:
                pass_pop = 0
                return render_template('contrasenia_admin.html', pass_pop=pass_pop,result_admin=result_admin, sucursal_admin=sucursal_admin,notificacionesIndex=notificacionesIndex)
        elif nuevaContraseniaAdministrador == contraseniaActualAdministrador:
            pass_pop = -1  
            return render_template('contrasenia_admin.html', pass_pop=pass_pop,result_admin=result_admin, sucursal_admin=sucursal_admin,notificacionesIndex=notificacionesIndex)     
        else:
            pass_pop = 1
            return render_template('contrasenia_admin.html', pass_pop=pass_pop,result_admin=result_admin, sucursal_admin=sucursal_admin,notificacionesIndex=notificacionesIndex)

@app.route('/download_pdf_registro_de_cuotas')
def download_pdf_registro_de_cuotas():
    # Datos para el reporte
    db = mysql.connection.cursor()
    id_administrador = session["id_administrador"]

    # Informacion del administrador 
    query="SELECT * FROM mostardatosadmin(%s);"
    db.execute(query,[id_administrador])
    admin_info = db.fetchall()

    # Deducciones 
    query = "SELECT * FROM obtenercuotasporpagar(%s);"
    db.execute(query,(id_administrador,))
    diccionario = crear_diccionario(db)
    monto_cuota = calcular_monto_cuota(diccionario)

    resultado = []

    for i, dato in enumerate(diccionario):
        resultado.append(
            {
                'numero_cuota': dato['NumeroDeCuota'],
                'nombre_colaborador': f"{dato['NombresColaborador']} {dato['ApellidosColaborador']}",
                'monto_pago': monto_cuota[i], 
            }
        )

    Fecha = diccionario[0]['FechaDePago']

    # Crear un archivo de memoria usando io.BytesIO
    pdf_buffer = io.BytesIO()
    
    # Llamar a la función para crear el reporte
    crearreportededucciones(pdf_buffer, admin_info, resultado,Fecha)
    
    # Mover el cursor al inicio del buffer
    pdf_buffer.seek(0)
    
    db.close()
    # Enviar el archivo al cliente
    return send_file(pdf_buffer, as_attachment=True, download_name='reporte_deducciones.pdf', mimetype='application/pdf')

@app.route('/download_pdf_contrato/<int:IdPrestamo>/<int:IdColaborador>/<int:IdSolicitudesPrestamos>')
def download_pdf_contrato(IdPrestamo, IdColaborador, IdSolicitudesPrestamos):
    db = mysql.connection.cursor()

    # Unidad de negocio
    query = "SELECT un.nombreUnidadDeNegocio FROM UnidadDeNegocio un JOIN Sucursales s on un.IdUnidadDeNegocio = s.IdUnidadDeNegocio JOIN Colaboradores c ON s.IdSucursal = c.IdSucursal WHERE c.IdColaborador = %s"
    db.execute(query, (IdColaborador,))
    unidadnegocio = db.fetchone()[0]

    # Información del colaborador solicitante
    query = """
        SELECT idcolaborador AS "IdColaborador",
               fechacontratacion AS "FechaContratacion",
               cedulacolaborador AS "CedulaColaborador",
               nombrescolaborador AS "NombresColaborador",
               apellidoscolaborador AS "ApellidosColaborador",
               salariocolaborador AS "SalarioColaborador",
               tipodecontrato AS "TipoDeContrato",
               estadocrediticio AS "EstadoCrediticio",
               correocolaborador AS "CorreoColaborador",
               numerotelefonocolaborador AS "NumeroTelefonoColaborador",
               contrasenia AS "Contrasenia",
               idsucursal AS "IdSucursal",
               estadocolaborador AS "EstadoColaborador"
        FROM mostraruncolaborador(%s)
    """
    db.execute(query, (IdColaborador,))
    diccionarioInfoColaborador = crear_diccionario(db)

    colaborador_info = []
    for dato in diccionarioInfoColaborador:
        colaborador_info.append(
            {
                'nombre': dato['NombresColaborador'] + " " + dato['ApellidosColaborador'],
                'estatus': dato['TipoDeContrato'],
                'telefono': dato['NumeroTelefonoColaborador']
            }
        )

    # Información de la solicitud
    query = """
        SELECT idsolicitudesprestamos AS "IdSolicitudesPrestamos",
               fechadesolicitud AS "FechaDeSolicitud",
               montosolicitado AS "MontoSolicitado",
               plazodepago AS "PlazoDePago",
               motivoprestamo AS "MotivoPrestamo",
               idcolaborador AS "IdColaborador",
               idadministrador AS "IdAdministrador"
        FROM solicitudesprestamos
        WHERE idcolaborador = %s AND idsolicitudesprestamos = %s
    """
    db.execute(query, (IdColaborador, IdSolicitudesPrestamos))
    diccionarioInfoSolicitud = crear_diccionario(db)

    solicitud_info = []
    for dato in diccionarioInfoSolicitud:
        solicitud_info.append(
            {
                'cantidad': dato['MontoSolicitado'],
                'fecha': dato['FechaDeSolicitud'],
                'plazo': dato['PlazoDePago'],
                'motivo': dato['MotivoPrestamo']
            }
        )

    # Antigüedad laboral
    query = "SELECT FechaContratacion FROM Colaboradores WHERE IdColaborador = %s"
    db.execute(query, (IdColaborador,))
    result = db.fetchone()

    if result:
        FechaDeContratacion = result[0]
        if isinstance(FechaDeContratacion, date):
            anos, meses = calcular_antiguedad_laboral(FechaDeContratacion)
            if anos == 0:
                antiguedad = f"Meses: {meses}"
            else:
                antiguedad = f"Años: {anos}, Meses: {meses}"
        else:
            antiguedad = "Fecha de contratación no válida"

    # Información del préstamo
    query = """
        SELECT idprestamo AS "IdPrestamo",
               fechadeaprobacion AS "FechaDeAprobacion",
               capital AS "Capital",
               intereses AS "Intereses",
               cuotas AS "Cuotas",
               plazodepago_meses AS "PlazoDePago_Meses"
        FROM prestamos
        WHERE idprestamo = %s
    """
    db.execute(query, (IdPrestamo,))
    diccionarioInfoprestamo = crear_diccionario(db)

    prestamo_info = []
    for dato in diccionarioInfoprestamo:
        prestamo_info.append(
            {
                'plazoPagoAprobado': dato['PlazoDePago_Meses'],
                'capital': dato['Capital'],
                'Intereses': dato['Intereses']
            }
        )

    # Deudas del colaborador
    query = "SELECT EstadoCrediticio FROM Colaboradores WHERE IdColaborador = %s"
    db.execute(query, (IdColaborador,))
    estado = db.fetchone()

    if estado and estado[0] == '1':
        debe = "Sí"
    else:
        debe = "No"

    # Crear PDF
    pdf_buffer = io.BytesIO()
    crear_contrato_prestamo(pdf_buffer, prestamo_info[0], solicitud_info[0], unidadnegocio, antiguedad, debe, colaborador_info[0])
    pdf_buffer.seek(0)
    db.close()

    return send_file(pdf_buffer, as_attachment=True, download_name='ContratoDePrestamo.pdf', mimetype='application/pdf')

@app.route('/download_pdf_prestamo_detallado/<int:IdPrestamo><string:CedulaColaborador>')
def download_pdf_prestamo_detallado(IdPrestamo,CedulaColaborador):
    db = mysql.connection.cursor()
    # autor
    tiporol = session.get('type')
    if tiporol == 'colaborador':
        autor = session["id_colaborador"]
        query = """
            SELECT nombrescolaborador AS "NombresColaborador",
                   apellidoscolaborador AS "ApellidosColaborador"
            FROM colaboradores
            WHERE idcolaborador = %s
        """
        db.execute(query,(autor,))
        autor = crear_diccionario(db)
        autor = autor[0]['NombresColaborador'] + " " + autor[0]['ApellidosColaborador']

    elif tiporol == "admin":
        autor = session["id_administrador"]
        query = """
            SELECT nombresadministrador AS "NombresAdministrador",
                   apellidosadministrador AS "ApellidosAdministrador"
            FROM administrador
            WHERE idadministrador = %s
        """
        db.execute(query,(autor,))
        autor= crear_diccionario(db)
        autor = autor[0]['NombresAdministrador'] + " " + autor[0]['ApellidosAdministrador']

    # Información del préstamo
    query = """
        SELECT idprestamo AS "IdPrestamo",
               fechadeaprobacion AS "FechaDeAprobacion",
               capital AS "Capital",
               intereses AS "Intereses",
               plazodepago_meses AS "PlazoDePago_Meses",
               cuotas AS "Cuotas",
               estadoprestamo AS "EstadoPrestamo"
        FROM prestamos
        WHERE idprestamo = %s
    """
    db.execute(query,(IdPrestamo,))
    diccionarioInfoprestamo = crear_diccionario(db)

    loan_info = []
    for dato in diccionarioInfoprestamo:
        prestamo = diccionarioInfoprestamo[0]
        loan_info.append(
            {
                'id': prestamo['IdPrestamo'],
                'fecha': prestamo['FechaDeAprobacion'],
                'capital': prestamo['Capital'],
                'tasa': prestamo['Intereses'] * 100,
                'total': prestamo['Capital'] + (prestamo['Capital'] * prestamo['Intereses'] * prestamo['Cuotas']),
                'plazo': prestamo['PlazoDePago_Meses'],
                'cuotas': prestamo['Cuotas'],
                'estado': prestamo['EstadoPrestamo'],
            }
        )
    
    # Información del prestatario (Colaborador)
    query="SELECT * FROM obtenerinfocolaboradorconidprestamo(%s);"
    db.execute(query,(IdPrestamo,))
    diccionarioInfoColaborador = crear_diccionario(db)

    borrower_info = []
    for dato in diccionarioInfoColaborador:
        borrower_info.append(
            {
                'nombre': dato['NombresColaborador'] + " " + dato['ApellidosColaborador'],
                'cedula': dato['CedulaColaborador'],
                'telefono': dato['NumeroTelefonoColaborador'],
            }
        )

    # Información del prestatario (Administrador)
    query="SELECT * FROM obtenerinfoadministradorconidprestamo(%s);"
    db.execute(query,(IdPrestamo,))
    diccionarioInfoAdministrador = crear_diccionario(db)

    #Info de la sucursal
    db.execute("SELECT nombredesucursal AS \"nombreDeSucursal\" FROM sucursales WHERE IdSucursal = %s;", (diccionarioInfoAdministrador[0]['IdSucursal'],))
    diccionarioSucursal = crear_diccionario(db)

    lender_info = []
    for dato in diccionarioInfoAdministrador:
        lender_info.append(
            {
                'nombre': dato['NombresAdministrador'] + " " + dato['ApellidosAdministrador'], 
                'cedula': dato['CedulaAdministrador'],
                'sucursal': diccionarioSucursal[0]['nombreDeSucursal'],  
                'telefono': dato['NumeroTelefonoAdministrador'],
            }
        )

    # Detalles de los pagos
    # buscar las fechas de pago segun el prestamo
    query = "SELECT FechaDePago FROM RegistroPagos WHERE IdPrestamo=%s;"
    db.execute(query,(IdPrestamo,))
    fechas_pago = db.fetchall()
    
    #retorno de la demas informacion sobre las cuotas
    query = "SELECT * FROM mostrarregistropagocolaboradorconidprestamo(%s)"
    db.execute(query,(IdPrestamo,))
    tabla = db.fetchall()

    # Creacion del diccionario 
    columns = [column[0] for column in db.description]
    tabla = [dict(zip(columns, row)) for row in tabla]

    id_colaborador = diccionarioInfoColaborador[0]['IdColaborador']

    db.execute("SELECT obtenerpagosdeducidosporidcolaborador(%s);",(id_colaborador,))
    cuotas_deducidas = db.fetchone()[0] 

    # funcion para calcular los pagos del prestamo 
    datos = calcular_pagos(tabla,fechas_pago,cuotas_deducidas)

    payment_details = []
    for dato in datos:
        payment_details.append(
            {
                'cuota': dato['contador'], 
                'fecha': dato['Fecha'], 
                'monto': dato['Pagos'], 
                'capital': dato['Capital'], 
                'intereses': dato['Interes'], 
                'saldo': dato['Saldo'],
                'estado': dato['EstadoCuota']
            }
        )
    
    # Crear un archivo de memoria usando io.BytesIO
    pdf_buffer = io.BytesIO()

    reporteprestamo(pdf_buffer, loan_info, borrower_info, lender_info, payment_details,autor)

    pdf_buffer.seek(0)
    db.close()
    # Enviar el archivo al cliente
    return send_file(pdf_buffer, as_attachment=True, download_name='ReporteDePrestamo.pdf', mimetype='application/pdf')

@app.route('/download_pdf_reporte/<string:Fecha>')
def download_pdf_reporte(Fecha):
    db = mysql.connection.cursor()
    # Datos para el reporte
    id_administrador = session["id_administrador"]
    cedula_administrador = session["cedula_administrador"]

    # Informacion del administrador 
    query="SELECT * FROM mostardatosadmin(%s);"
    db.execute(query,[id_administrador])
    admin_info = db.fetchall()

    # Deducciones 
    # Gerente General
    if cedula_administrador  == "000-000000-0000A":
        query = "SELECT * FROM obtenercuotasporpagarhistorialgerente(%s);"
        db.execute(query,[Fecha])
        diccionario = crear_diccionario(db)
    else:
        query = "SELECT * FROM obtenercuotasporpagarhistorial(%s, %s);"
        db.execute(query,[id_administrador,Fecha])
        diccionario = crear_diccionario(db)

    monto_cuota = calcular_monto_cuota(diccionario)
    resultado = []

    for i, dato in enumerate(diccionario):
        resultado.append(
            {
                'numero_cuota': dato['NumeroDeCuota'],
                'nombre_colaborador': f"{dato['NombresColaborador']} {dato['ApellidosColaborador']}",
                'monto_pago': monto_cuota[i], 
            }
        )

    # Crear un archivo de memoria usando io.BytesIO
    pdf_buffer = io.BytesIO()
    
    # Llamar a la función para crear el reporte
    crearreportededucciones(pdf_buffer, admin_info, resultado,Fecha)
    pdf_buffer.seek(0)
    db.close()
    # Enviar el archivo al cliente
    return send_file(pdf_buffer, as_attachment=True, download_name='ReporteCuotas.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(port = 5001)
