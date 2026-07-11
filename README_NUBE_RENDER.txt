ASESORÍA HORAS - VERSIÓN NUBE / RENDER
======================================

Objetivo:
Publicar la aplicación en Internet para que pueda usarse desde celular,
tablet o PC sin estar en la misma red local.

ARCHIVOS IMPORTANTES
--------------------
app.py                  Aplicación Flask preparada para nube.
requirements.txt        Dependencias Python.
Procfile                Comando de arranque compatible con plataformas tipo Heroku.
render.yaml             Configuración tipo Blueprint para Render.
runtime.txt             Versión sugerida de Python.
templates/              Pantallas HTML.
static/                 Estilos, icono y PWA.

USUARIOS INICIALES
------------------
Administrador:
  usuario: admin
  clave: admin123

Usuario de prueba:
  usuario: consultor
  clave: 123456

IMPORTANTE:
Cambiar la clave del administrador antes de uso real.
En Render puedes cambiar ADMIN_PASSWORD en Environment Variables.

DESPLIEGUE RECOMENDADO EN RENDER
---------------------------------
1. Crear una cuenta en Render.
2. Crear o usar una cuenta GitHub.
3. Crear un repositorio nuevo, por ejemplo:
   asesoria-horas
4. Subir todos los archivos de esta carpeta al repositorio.
5. En Render seleccionar:
   New + > Blueprint
6. Conectar el repositorio que contiene render.yaml.
7. Render creará:
   - Un Web Service para la app.
   - Una base de datos PostgreSQL.
8. Al terminar, Render entregará una URL pública, por ejemplo:
   https://asesoria-horas.onrender.com
9. Entrar con admin/admin123, crear usuarios reales y luego dejar de usar el usuario de prueba.

ALTERNATIVA MANUAL EN RENDER
----------------------------
Si no usas Blueprint:

Build Command:
  pip install -r requirements.txt

Start Command:
  gunicorn app:app

Variables de entorno:
  SECRET_KEY       una clave larga y privada
  DATABASE_URL     la URL de la base PostgreSQL
  ADMIN_USER       admin
  ADMIN_PASSWORD   una clave segura
  ADMIN_NAME       Administrador del Equipo
  CREATE_DEMO_DATA true o false

BASE DE DATOS
-------------
La app usa PostgreSQL cuando existe DATABASE_URL.
Si no existe DATABASE_URL, usa SQLite local para pruebas.

NOTA SOBRE PLANES GRATUITOS
---------------------------
En servicios gratuitos puede haber pausas, reinicios o límites.
Para operación real, se recomienda un plan con base de datos persistente,
respaldos y HTTPS activo.

PRUEBA LOCAL
------------
Instalar dependencias:
  pip install -r requirements.txt

Ejecutar:
  python app.py

Abrir:
  http://127.0.0.1:5000


PANTALLA DE INICIO PUBLICA
--------------------------

La aplicación ahora abre primero una pantalla de inicio pública en /.
Desde el botón "Comenzar" el usuario pasa al login y luego al panel interno.
El panel principal autenticado quedó en /panel.

PANTALLA DE INICIO PROFESIONAL
------------------------------

Esta versión incluye una portada pública más trabajada visualmente:

- Hero superior con fondo oscuro estilo imagen corporativa.
- Título principal y botón "Comenzar".
- Tarjetas de beneficios.
- Pie visual con referencia a redes.
- Flujo: / inicio público, /login ingreso, /panel dashboard interno.

MEJORA ADMIN / CELULAR
----------------------

Cambios incorporados:

- El dashboard queda reservado solo para el usuario administrador.
- Los usuarios normales ingresan directamente a "Nuevo registro".
- La navegación de usuarios normales ya no muestra "Panel".
- La pantalla de inicio ya no incluye la sección "Por qué usar esta app".
- Se ajustó la vista móvil para una experiencia más limpia en celular.
