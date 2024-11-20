#Instalación y configuración de Agente:

Compilación de agente:

´´´
pip install pyinstaller
pyinstaller --onefile agente.py

Mover la ruta
mv dist/agente /usr/local/bin/

Creando el servicio
sudo nano /etc/systemd/system/monitor.service

[Unit]
Description=Monitor Agent Service
After=network.target

[Service]
ExecStart=/usr/local/bin/agente
Restart=always
User=root
Group=root
StandardOutput=journal
StandardError=journal
Environment=PATH=/usr/bin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/local/sbin

[Install]
WantedBy=multi-user.target


sudo systemctl daemon-reload
sudo systemctl enable monitor.service
sudo systemctl start monitor.service
sudo systemctl status monitor.service

´´´
