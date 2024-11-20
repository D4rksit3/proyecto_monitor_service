import os
import subprocess
import socketio
import socket
import time
import psutil  # Usaremos psutil para obtener la dirección IPv4 real

# Conectar con el servidor Flask usando SocketIO
sio = socketio.Client()

# Dirección del servidor
SERVER_URL = "http://{ip}:4444"


@sio.event
def restart(data):
    service = data['service']
    print(f"Solicitud de reinicio recibida para el servicio {service}")
    time.sleep(5)
    # Intentar reiniciar el servicio
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', service], check=True)
        print(f"Servicio {service} reiniciado con éxito.")
    except subprocess.CalledProcessError as e:
        print(f"Error al intentar reiniciar el servicio {service}: {e}")


# Identificar el servicio web activo
def identify_service():
    print("Verificando servicios activos...")  # Para depuración
    services = ["apache2", "httpd", "tomcat"]
    for service in services:
        status = subprocess.run(["systemctl", "is-active", service], stdout=subprocess.PIPE)
        print(f"Verificando servicio {service}, estado: {status.stdout.decode().strip()}")  # Depuración
        if status.stdout.decode().strip() == "active":
            print(f"Servicio {service} está activo.")  # Depuración
            return service
    print("No se encontró un servicio web activo.")  # Depuración
    return None

# Obtener información del servicio
def get_service_info(service):
    print(f"Obteniendo información de {service}...")  # Depuración
    version = subprocess.run([service, "-v"], stdout=subprocess.PIPE).stdout.decode().strip()
    domains_path = {
        "apache2": "/etc/apache2/sites-enabled/",
        "httpd": "/etc/httpd/conf.d/",
        "tomcat": "/etc/tomcat/conf/"
    }
    try:
        domains = os.listdir(domains_path.get(service, "/etc/"))
    except FileNotFoundError:
        domains = []  # Si no encuentra el directorio, asume que no hay dominios
    print(f"Dominios encontrados para {service}: {domains}")  # Depuración
    return {
        "service": service,
        "version": version,
        "domains": domains
    }

# Obtener la dirección IPv4 real del equipo
def get_ipv4_address():
    print("Obteniendo dirección IPv4...")  # Para depuración
    # Iterar sobre las interfaces de red
    for interface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            # Buscar la dirección IPv4 (familia de direcciones AF_INET)
            if addr.family == socket.AF_INET:
                # Filtrar las direcciones locales (como 127.0.0.1) y devolver la primera dirección IPv4 válida
                if addr.address != "127.0.0.1":
                    print(f"Interfaz: {interface}, Dirección IPv4: {addr.address}")  # Depuración
                    return addr.address
    print("No se encontró una dirección IPv4 válida.")  # Depuración
    return None

# Obtener el hostname del equipo
def get_hostname():
    hostname = socket.gethostname()  # Obtiene el nombre del equipo
    print(f"Hostname: {hostname}")  # Depuración
    return hostname

# Función para conectarse al servidor
def connect_to_server():
    print("Conectándose al servidor en el puerto 4444...")
    sio.connect(SERVER_URL)
    print("Conectado al servidor en el puerto 4444")

# Enviar datos al servidor
def send_data_to_server(data):
    print(f"Enviando datos al servidor: {data}")  # Muestra los datos antes de enviarlos
    sio.emit('monitor', data)
    print(f"Datos del servicio {data['service']} enviados al servidor.")  # Depuración

# Enviar reinicio de servicio
def send_restart_request(service):
    sio.emit('restart', service)
    print(f"Solicitud de reinicio para el servicio: {service}")  # Depuración

# Monitorear el servicio
def monitor():
    print("Iniciando monitoreo del servicio...")  # Depuración
    service = identify_service()
    if service:
        hostname = get_hostname()  # Obtener el hostname
        ip_address = get_ipv4_address()  # Obtener la dirección IPv4 real
        if ip_address:  # Si encontramos una IP válida
            data = get_service_info(service)
            data['hostname'] = hostname
            data['ip_address'] = ip_address
            send_data_to_server(data)
        else:
            print("No se pudo obtener una dirección IPv4 válida.")  # Depuración
    else:
        print("Enviando datos de agente sin servicio web...")  # Depuración
        hostname = get_hostname()  # Obtener el hostname
        ip_address = get_ipv4_address()  # Obtener la dirección IPv4
        if ip_address:  # Si encontramos una IP válida
            data = {
                'service': 'No service',
                'hostname': hostname,
                'ip_address': ip_address,
                'status': 'down'
            }
            send_data_to_server(data)

# Función principal del ciclo
def run_agent():
    connect_to_server()  # Conéctate al servidor antes de iniciar el monitoreo
    while True:
        monitor()  # Monitorea el servicio en tiempo real
        time.sleep(10)  # Espera 10 segundos antes de volver a comprobar el estado del servicio

# Ejecutar el agente
if __name__ == "__main__":
    run_agent()