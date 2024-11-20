from flask import Flask, render_template, request, redirect, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from flask_socketio import SocketIO, emit
from datetime import datetime
from datetime import timedelta




# Inicializamos la aplicación Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://jroque:123456@localhost/service_monitoring'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

# Inicializamos SocketIO
socketio = SocketIO(app)

login_manager.login_view = 'login'

# Modelo de usuario con contraseñas en texto plano
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    def set_password(self, password):
        self.password = password  # Almacena la contraseña en texto plano

    def check_password(self, password):
        return self.password == password  # Verifica la contraseña directamente

# Función user_loader para cargar al usuario desde la base de datos
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Modelo de servicio para almacenar la información de los agentes
class Service(db.Model):
    id = db.Column(db.String(150), primary_key=True, nullable=False)  # Usamos el hostname como id
    service_name = db.Column(db.String(150), nullable=False)
    version = db.Column(db.String(150), nullable=False, default='N/A')  # Valor por defecto 'N/A'
    domains = db.Column(db.Text, nullable=False, default='[]')  # Valor por defecto para dominios
    status = db.Column(db.String(20), default='active')
    hostname = db.Column(db.String(150), nullable=False)
    ip_address = db.Column(db.String(150), nullable=False)
    last_status_change = db.Column(db.DateTime, default=datetime.utcnow)  # Fecha del último cambio de estado

# Modelo de log para registrar los eventos
class ServiceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.String(150), db.ForeignKey('service.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(150), nullable=False)

    # Relación con el modelo Service
    service = db.relationship('Service', backref=db.backref('logs', lazy=True))

    # Método para serializar el objeto a un diccionario
    def to_dict(self):
        return {
            'id': self.id,
            'service_id': self.service_id,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'action': self.action
        }

# Ruta para obtener los logs del servicio
@app.route('/get_logs')
def get_logs():
    try:
        # Obtener el hostname y el filtro de tiempo desde la solicitud
        hostname = request.args.get('hostname')
        time_filter = request.args.get('time_filter', '3h')  # Por defecto, 3 horas

        # Validar hostname
        if not hostname:
            return jsonify({"error": "Hostname no proporcionado"}), 400

        # Obtener la fecha y hora actual
        now = datetime.utcnow()

        # Calcular el límite de tiempo según el filtro seleccionado
        if time_filter == '3h':
            time_limit = now - timedelta(hours=3)
        elif time_filter == '24h':
            time_limit = now - timedelta(hours=24)
        elif time_filter == '1w':
            time_limit = now - timedelta(weeks=1)
        else:
            return jsonify({"error": "Filtro de tiempo no válido"}), 400

        # Obtener los logs de la base de datos relacionados con ese hostname y filtrados por tiempo
        logs = ServiceLog.query.filter(
            ServiceLog.service_id == hostname,
            ServiceLog.timestamp >= time_limit
        ).all()

        # Si no se encuentran logs, devolver mensaje vacío
        if not logs:
            return jsonify({"message": "No se encontraron logs para el rango de tiempo especificado"}), 200

        # Serializar los logs a un formato JSON
        logs_data = [log.to_dict() for log in logs]

        # Devolver los logs como JSON
        return jsonify(logs_data), 200
    except Exception as e:
        # Manejar errores generales
        return jsonify({"error": f"Ha ocurrido un error: {str(e)}"}), 500



# Ruta para el login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)  # Inicia la sesión del usuario
            return redirect('/dashboard')
        else:
            flash('Login failed. Check your username and/or password', 'danger')
            return redirect('/login')
    
    return render_template('login.html')

# Ruta del dashboard, protegida por login_required
@app.route('/dashboard')
@login_required
def dashboard():
    # Obtener los servicios activos desde la base de datos
    services = Service.query.all()
    
    # Obtener los logs de servicio para cada servicio
    service_logs = ServiceLog.query.all()

    # Convertir los ServiceLog en un formato serializable (lista de diccionarios)
    service_logs_data = [
        {
            'service_id': log.service_id,
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'action': log.action
        }
        for log in service_logs
    ]
    
    return render_template('dashboard.html', services=services, service_logs=service_logs_data)


# Ruta de logout
@app.route('/logout')
def logout():
    logout_user()
    return redirect('/login')

@socketio.on('restart')
def handle_restart(service):
    result = subprocess.run(["systemctl", "restart", service], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        emit('status', {'message': f'{service} restarted successfully!'})
    else:
        emit('status', {'message': f'Error restarting {service}: {result.stderr.decode()}'})


# Función para manejar el evento de monitorización
@socketio.on('monitor')
def handle_monitor(data):
    print("Datos recibidos del agente:", data)  # Para depuración

    # Extraer los datos del servicio
    service_name = data['service']
    hostname = data['hostname']
    ip_address = data['ip_address']
    
    # Determinar el estado del servicio
    if service_name == 'No service':
        status = 'down'  # El servicio está caído
        action = "Servicio caído detectado"
    else:
        status = 'active'  # El servicio está activo
        action = "Servicio activo"
    
    # Verificar si el servicio existe en la base de datos
    service = Service.query.filter_by(hostname=hostname).first()  # Filtramos por hostname

    # Si el servicio existe, actualizamos su estado; si no, lo creamos
    if service:
        service.status = status  # Actualizamos el estado del servicio
        service.ip_address = ip_address  # Actualizamos la IP en caso de cambio
    else:
        # Si el servicio no existe, lo creamos
        if not data.get('version'):
            data['version'] = 'N/A'  # Asignar 'N/A' si la versión no está presente
        
        if not data.get('domains'):
            data['domains'] = []  # Asignar una lista vacía si no hay dominios

        service = Service(
            id=hostname,
            service_name=service_name,
            version=data.get('version', 'N/A'),
            domains=', '.join(data.get('domains', [])),
            status=status,
            hostname=hostname,
            ip_address=ip_address
        )
        db.session.add(service)

    db.session.commit()  # Guardamos los cambios en el servicio

    # Guardamos el log del servicio (IP y estado)
    service_log = ServiceLog(
        service_id=hostname,  # Usamos hostname como ID del servicio
        action=action
    )
    db.session.add(service_log)
    db.session.commit()  # Guardamos el log

    # Emitir un mensaje de confirmación al cliente
    emit('status', {
        'hostname': hostname,
        'status': status,
        'last_status_change': service.last_status_change.strftime('%Y-%m-%d %H:%M:%S')
    }, broadcast=True)

    # Si el servicio está "caído" (sin servicio web), intentar reiniciar
    if status == 'down':
        print(f"Servicio caído detectado en el agente {hostname}. Intentando reiniciar...")
        emit('restart', {'service': 'apache2'}, broadcast=True)  # Ajusta el servicio según sea necesario
# Emitir el nuevo estado del servicio a todos los clientes
    socketio.emit('update_table', {
    'id': service.id,
    'hostname': service.hostname,
    'ip_address': service.ip_address,
    'status': service.status,
    'last_status_change': service.last_status_change.strftime('%Y-%m-%d %H:%M:%S')
    })









# Iniciar la aplicación
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=4444, debug=True)
