# Mateo Bloom & Bite

Catálogo, preventa y asistente virtual para la feria de la Unidad Educativa Particular Cavanis, Santo Domingo.

## Inicio local
Python 3.10 o superior. Configura una contraseña única de al menos 12 caracteres y ejecuta:

```bash
export BLOOM_ADMIN_PASSWORD='CAMBIAR_POR_CLAVE_SEGURA'
export BLOOM_NOTIFY_EMAIL='mateodanielringo@gmail.com'
python3 server.py
```

Visita `http://127.0.0.1:8080/`. Panel: `/admin`, usuario `admin`. Abrir index.html directamente no permite reservar.

## Publicación
GitHub guarda el código, pero GitHub Pages solo sirve contenido estático: no ejecuta este servidor ni puede guardar reservas de forma segura. Crea un repositorio nuevo (preferiblemente privado), sube los archivos y conecta un alojamiento de contenedores/Python con HTTPS y un volumen persistente en `/app/data`. El Dockerfile incluido usa `PORT` (8080 por defecto). No publiques la base de datos ni las credenciales. Configura el proxy y las protecciones de abuso del alojamiento antes de anunciar el sitio.

Variables del servidor:
- `BLOOM_ADMIN_PASSWORD`: contraseña privada larga.
- `BLOOM_NOTIFY_EMAIL`: destinatario de avisos (el correo del propietario).
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: proveedor de envío autorizado. Si usas Gmail y tu cuenta admite contraseñas de aplicaciones, usa `smtp.gmail.com`, puerto 587 y una contraseña de aplicación, no la contraseña normal.
- `BLOOM_DB`: ruta de base persistente (por defecto `data/bloom.sqlite3`).
- `BLOOM_CAPACITY`: JSON de cupos por producto, según la producción real. Por defecto `{"0":6,"1":3,"2":2,"3":12,"4":12,"5":2}` (37 unidades propuestas, no inventario verificado). Cambiar antes de publicar. Cada producto tiene un cupo independiente: planifica aparte las materias primas compartidas.

Las reservas de catálogo ocupan cupo al guardarse. Las solicitudes personalizadas no comprometen disponibilidad ni precio. Se genera un código y el aviso queda en una cola persistente; se reintenta cada 30 segundos si falla. No hay pago en línea. WhatsApp es solo para coordinación posterior. El propietario debe comprobar la entrega del primer correo antes de anunciar la preventa; la revisión de Gmail ya se gestiona aparte.

## Privacidad
Los datos de contacto y pedidos solo se guardan para gestionar la feria. El panel requiere contraseña y las métricas de actividad son anónimas y optativas. Elimina los registros y copias de seguridad al finalizar el plazo informado (30 días después de la feria), salvo obligaciones legales. Los correos también deben eliminarse cuando ya no sean necesarios. No publicar archivos `data/`, `.env` ni credenciales.

## Crear el repositorio desde Linux
Con GitHub CLI (`gh`) y Git instalados, ejecuta `bash publicar_github.sh`. El script autentica de forma interactiva si hace falta, verifica que la cuenta sea `mateonunezdev`, ejecuta las pruebas locales y crea un repositorio privado nuevo. No sobrescribe repositorios existentes. Git debe tener configurados el nombre y correo del autor de los commits. La autenticación ocurre directamente en GitHub; no compartas tokens ni contraseñas por chat.

## Pruebas
`python3 test_reservas.py` comprueba reservas, duplicados, cupos, pedidos personalizados, cola de avisos y ambos modos SMTP mediante un transporte simulado. No verifica la entrega real. Para activarla, configura las variables SMTP directamente en el alojamiento y comprueba una reserva de prueba con consentimiento.