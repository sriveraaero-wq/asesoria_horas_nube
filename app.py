from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from io import BytesIO, StringIO
from datetime import datetime
import os
import csv
import zipfile
import html
import re


def normalize_database_url(url: str | None) -> str:
    """Render/Heroku sometimes provide postgres://. SQLAlchemy expects postgresql://."""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url or "sqlite:///instance/asesoria_horas.db"


app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambiar-esta-clave-en-produccion")
app.config["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(os.environ.get("DATABASE_URL"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# En Render/PG ayuda a mantener conexiones sanas después de reinicios o pausas.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.String(32), nullable=False)

    records = db.relationship("Record", back_populates="user", lazy="select")


class Record(db.Model):
    __tablename__ = "records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    fecha = db.Column(db.String(10), nullable=False, index=True)
    empresa = db.Column(db.String(160), nullable=False, index=True)
    proyecto = db.Column(db.String(160), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=False)
    horas = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(50), nullable=False)
    consultor = db.Column(db.String(160), nullable=False, index=True)
    observaciones = db.Column(db.Text)
    created_at = db.Column(db.String(32), nullable=False)
    updated_at = db.Column(db.String(32), nullable=False)

    user = db.relationship("User", back_populates="records", lazy="joined")

    @property
    def username(self):
        return self.user.username if self.user else ""

    @property
    def full_name(self):
        return self.user.full_name if self.user else ""


def init_db():
    db.create_all()
    now = datetime.now().isoformat(timespec="seconds")

    admin_user = os.environ.get("ADMIN_USER", "admin").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    admin_name = os.environ.get("ADMIN_NAME", "Administrador del Equipo")

    admin = User.query.filter_by(username=admin_user).first()
    if not admin:
        admin = User(
            username=admin_user,
            password_hash=generate_password_hash(admin_password),
            full_name=admin_name,
            role="admin",
            active=True,
            created_at=now,
        )
        db.session.add(admin)

    create_demo = os.environ.get("CREATE_DEMO_DATA", "true").lower() in {"1", "true", "yes", "si", "sí"}
    demo_user = User.query.filter_by(username="consultor").first()
    if create_demo and not demo_user:
        demo_user = User(
            username="consultor",
            password_hash=generate_password_hash("123456"),
            full_name="Consultor de Prueba",
            role="user",
            active=True,
            created_at=now,
        )
        db.session.add(demo_user)
        db.session.flush()

        demo_records = [
            ("2026-07-01", "AAP", "Arequipa RWY", "Análisis de propuesta final", 3.0, "En proceso", "Consultor de Prueba", "Se analizó la propuesta y se elabora presentación."),
            ("2026-07-02", "AAP", "EDI Juliaca", "Revisión de información técnica", 5.0, "Completado", "Consultor de Prueba", "Se revisó documentación inicial y se dejaron comentarios."),
            ("2026-07-03", "AAP", "EDI Juliaca", "Preparación de resumen ejecutivo", 7.0, "En revisión", "Consultor de Prueba", "Pendiente validación del equipo técnico."),
            ("2026-07-04", "AAP", "FBO", "Reunión de coordinación y observaciones", 1.0, "Pendiente", "Consultor de Prueba", "Se requiere ampliar información de alcance."),
            ("2026-07-05", "AAP", "EDI Juliaca", "Actualización del cuadro de control", 10.0, "En proceso", "Consultor de Prueba", "Se consolidan horas del periodo."),
        ]
        for row in demo_records:
            db.session.add(
                Record(
                    user_id=demo_user.id,
                    fecha=row[0],
                    empresa=row[1],
                    proyecto=row[2],
                    descripcion=row[3],
                    horas=row[4],
                    estado=row[5],
                    consultor=row[6],
                    observaciones=row[7],
                    created_at=now,
                    updated_at=now,
                )
            )

    db.session.commit()


@app.before_request
def load_logged_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        if not g.user.active:
            session.clear()
            flash("Usuario inactivo. Contacte al administrador.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        if g.user.role != "admin":
            flash("Esta opción es solo para el administrador.", "error")
            return redirect(url_for("panel" if user.role == "admin" else "nuevo"))
        return view(*args, **kwargs)
    return wrapped_view


def apply_record_scope(query, params):
    if g.user.role != "admin":
        query = query.filter(Record.user_id == g.user.id)

    if params.get("empresa"):
        query = query.filter(Record.empresa == params["empresa"])
    if params.get("proyecto"):
        query = query.filter(Record.proyecto == params["proyecto"])
    if params.get("consultor"):
        query = query.filter(Record.consultor == params["consultor"])
    if params.get("fecha_desde"):
        query = query.filter(Record.fecha >= params["fecha_desde"])
    if params.get("fecha_hasta"):
        query = query.filter(Record.fecha <= params["fecha_hasta"])
    return query


def fetch_records(params=None, limit=None):
    params = params or {}
    query = Record.query
    query = apply_record_scope(query, params).order_by(Record.fecha.desc(), Record.id.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def fetch_distinct(field):
    allowed = {"empresa": Record.empresa, "proyecto": Record.proyecto, "consultor": Record.consultor, "estado": Record.estado}
    column = allowed.get(field)
    if column is None:
        return []
    query = db.session.query(column).distinct().order_by(column)
    if g.user.role != "admin":
        query = query.filter(Record.user_id == g.user.id)
    return [row[0] for row in query.all() if row[0]]


def filters_context():
    return {
        "empresa": request.args.get("empresa", ""),
        "proyecto": request.args.get("proyecto", ""),
        "consultor": request.args.get("consultor", ""),
        "fecha_desde": request.args.get("fecha_desde", ""),
        "fecha_hasta": request.args.get("fecha_hasta", ""),
        "group_by": request.args.get("group_by", "empresa"),
        "empresas": fetch_distinct("empresa"),
        "proyectos": fetch_distinct("proyecto"),
        "consultores": fetch_distinct("consultor"),
    }


def record_value(record, field):
    return getattr(record, field) or "Sin dato"


def calc_dashboard(records, group_by):
    total_horas = sum(float(r.horas or 0) for r in records)
    empresas = len(set(r.empresa for r in records if r.empresa))
    proyectos = len(set(r.proyecto for r in records if r.proyecto))
    registros = len(records)
    promedio = total_horas / registros if registros else 0

    def group(field):
        data = {}
        for r in records:
            key = record_value(r, field)
            data[key] = data.get(key, 0) + float(r.horas or 0)
        ordered = sorted(data.items(), key=lambda item: item[1], reverse=True)
        max_val = ordered[0][1] if ordered else 0
        return [
            {"name": k, "hours": v, "pct": (v / max_val * 100) if max_val else 0}
            for k, v in ordered
        ]

    selected_field = group_by if group_by in {"empresa", "proyecto", "consultor"} else "empresa"
    selected = group(selected_field)
    return {
        "total_horas": total_horas,
        "empresas": empresas,
        "proyectos": proyectos,
        "registros": registros,
        "promedio": promedio,
        "selected": selected,
        "empresa_bars": group("empresa"),
        "proyecto_bars": group("proyecto"),
        "top": selected[0] if selected else None,
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.active and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("panel"))
        flash("Usuario o contraseña no válidos.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/panel")
@login_required
def panel():
    if g.user.role != "admin":
        return redirect(url_for("nuevo"))
    filt = filters_context()
    records = fetch_records(filt)
    dashboard = calc_dashboard(records, filt["group_by"])
    return render_template("panel.html", filters=filt, dashboard=dashboard)


@app.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        now = datetime.now().isoformat(timespec="seconds")
        try:
            horas = float(request.form.get("horas") or 0)
        except ValueError:
            horas = 0
        data = {
            "fecha": request.form.get("fecha", "").strip(),
            "empresa": request.form.get("empresa", "").strip(),
            "proyecto": request.form.get("proyecto", "").strip(),
            "descripcion": request.form.get("descripcion", "").strip(),
            "horas": horas,
            "estado": request.form.get("estado", "").strip(),
            "consultor": request.form.get("consultor", "").strip() or g.user.full_name,
            "observaciones": request.form.get("observaciones", "").strip(),
        }
        if not data["fecha"] or not data["empresa"] or not data["proyecto"] or not data["descripcion"] or data["horas"] <= 0:
            flash("Complete los campos obligatorios y asegure que las horas sean mayores a cero.", "error")
            return render_template("nuevo.html", today=datetime.now().date().isoformat(), form=data)

        db.session.add(
            Record(
                user_id=g.user.id,
                fecha=data["fecha"],
                empresa=data["empresa"],
                proyecto=data["proyecto"],
                descripcion=data["descripcion"],
                horas=data["horas"],
                estado=data["estado"],
                consultor=data["consultor"],
                observaciones=data["observaciones"],
                created_at=now,
                updated_at=now,
            )
        )
        db.session.commit()
        flash("Registro guardado correctamente.", "ok")
        return redirect(url_for("registros"))
    return render_template("nuevo.html", today=datetime.now().date().isoformat(), form={"consultor": g.user.full_name})


@app.route("/registros")
@login_required
def registros():
    latest = fetch_records({}, limit=4)
    return render_template("registros.html", records=latest)


@app.route("/detalle/<int:record_id>")
@login_required
def detalle(record_id):
    query = Record.query.filter(Record.id == record_id)
    if g.user.role != "admin":
        query = query.filter(Record.user_id == g.user.id)
    record = query.first()

    if not record:
        flash("Registro no encontrado o sin permiso para verlo.", "error")
        return redirect(url_for("registros"))

    return render_template("detalle.html", record=record)


@app.route("/datos")
@login_required
def datos():
    filt = filters_context()
    records = fetch_records(filt)
    return render_template("datos.html", records=records, filters=filt)


@app.route("/exportar/excel")
@login_required
def exportar_excel():
    filt = filters_context()
    records = fetch_records(filt)
    dashboard = calc_dashboard(records, filt["group_by"])
    data = build_xlsx(records, dashboard, filt)
    filename = f"asesoria_horas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/exportar/csv")
@login_required
def exportar_csv():
    filt = filters_context()
    records = fetch_records(filt)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Fecha", "Empresa", "Proyecto", "Descripcion", "Horas", "Estado", "Consultor", "Observaciones", "Usuario"])
    for r in records:
        writer.writerow([r.fecha, r.empresa, r.proyecto, r.descripcion, r.horas, r.estado, r.consultor, r.observaciones, r.username])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=asesoria_horas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"},
    )


@app.route("/admin/usuarios", methods=["GET", "POST"])
@admin_required
def admin_usuarios():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        if not re.match(r"^[a-zA-Z0-9_.-]{3,30}$", username):
            flash("El usuario debe tener 3 a 30 caracteres y solo usar letras, números, punto, guion o guion bajo.", "error")
        elif not full_name or len(password) < 6 or role not in {"admin", "user"}:
            flash("Complete nombre, rol y una contraseña mínima de 6 caracteres.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Ese nombre de usuario ya existe.", "error")
        else:
            db.session.add(
                User(
                    username=username,
                    password_hash=generate_password_hash(password),
                    full_name=full_name,
                    role=role,
                    active=True,
                    created_at=datetime.now().isoformat(timespec="seconds"),
                )
            )
            db.session.commit()
            flash("Usuario creado correctamente.", "ok")

    users = User.query.order_by(User.role, User.full_name).all()
    return render_template("admin_usuarios.html", users=users)


@app.route("/admin/usuarios/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    if user_id == g.user.id:
        flash("No puede desactivar su propio usuario.", "error")
        return redirect(url_for("admin_usuarios"))
    user = db.session.get(User, user_id)
    if user:
        user.active = not user.active
        db.session.commit()
        flash("Estado del usuario actualizado.", "ok")
    return redirect(url_for("admin_usuarios"))


def xlsx_escape(value):
    return html.escape(str(value if value is not None else ""), quote=False)


def col_name(n):
    name = ""
    while n:
        n, rem = divmod(n - 1, 26)
        name = chr(65 + rem) + name
    return name


def sheet_xml(rows):
    xml_rows = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            ref = f"{col_name(c_idx)}{r_idx}"
            if isinstance(value, (int, float)) and value is not None:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xlsx_escape(value)}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    {''.join(xml_rows)}
  </sheetData>
</worksheet>'''


def build_xlsx(records, dashboard, filters):
    registros_rows = [["Fecha", "Empresa", "Proyecto", "Descripción", "Horas", "Estado", "Consultor", "Observaciones", "Usuario"]]
    for r in records:
        registros_rows.append([r.fecha, r.empresa, r.proyecto, r.descripcion, float(r.horas or 0), r.estado, r.consultor, r.observaciones, r.username])

    resumen_rows = [
        ["Asesoría Horas - Resumen"],
        ["Generado", datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Empresa filtro", filters.get("empresa") or "Todas"],
        ["Proyecto filtro", filters.get("proyecto") or "Todos"],
        ["Consultor filtro", filters.get("consultor") or "Todos"],
        ["Fecha desde", filters.get("fecha_desde") or "Inicio abierto"],
        ["Fecha hasta", filters.get("fecha_hasta") or "Fin abierto"],
        [],
        ["Indicador", "Valor"],
        ["Total de horas", round(dashboard["total_horas"], 2)],
        ["Clientes / empresas", dashboard["empresas"]],
        ["Proyectos", dashboard["proyectos"]],
        ["Registros", dashboard["registros"]],
        ["Promedio horas por registro", round(dashboard["promedio"], 2)],
        [],
        ["Distribución seleccionada", "Horas"],
    ]
    for item in dashboard["selected"]:
        resumen_rows.append([item["name"], round(item["hours"], 2)])

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>'''

    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Registros" sheetId="1" r:id="rId1"/>
    <sheet name="Resumen" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>'''

    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>'''

    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml(registros_rows))
        z.writestr("xl/worksheets/sheet2.xml", sheet_xml(resumen_rows))
    return bio.getvalue()


with app.app_context():
    init_db()


if __name__ == "__main__":
    print("Asesoría Horas Equipo iniciado.")
    print("Abrir localmente: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
