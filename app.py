import os
import requests
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from supabase import create_client, Client
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
import secrets

load_dotenv()

app = Flask(__name__)
app.secret_key = 'tecnobots2026-clave-segura-para-sesiones-12345'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_TYPE'] = 'filesystem'

# Configuración de Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Configuración de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========== CONFIGURACIÓN DE ADMIN ==========
def cargar_admin_password():
    """Carga la contraseña del administrador desde Supabase"""
    try:
        response = supabase.table("configuracion").select("valor").eq("clave", "admin_password").execute()
        print(f"🔍 cargar_admin_password - Respuesta: {response.data}")
        
        if response.data and len(response.data) > 0:
            password = response.data[0]['valor']
            print(f"✅ Contraseña cargada: {password}")
            return password
        else:
            print("⚠️ No se encontró admin_password, creando...")
            supabase.table("configuracion").insert({"clave": "admin_password", "valor": "TECNO2026"}).execute()
            return "TECNO2026"
    except Exception as e:
        print(f"❌ Error en cargar_admin_password: {e}")
        return "TECNO2026"

# Al inicio del archivo, después de definir ADMIN_USER
ADMIN_PASS = cargar_admin_password()
print(f"🔐 ADMIN_PASS final: {ADMIN_PASS}")

def guardar_admin_password(nueva_password):
    """Guarda la nueva contraseña del administrador en Supabase"""
    try:
        print(f"🔐 Intentando guardar: {nueva_password}")
        # Usar upsert en lugar de update
        result = supabase.table("configuracion").upsert({"clave": "admin_password", "valor": nueva_password}).execute()
        print(f"📦 Resultado upsert: {result}")
        return True
    except Exception as e:
        print(f"❌ Error guardando: {e}")
        return False
# ========== MODELO DE USUARIO ==========
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.email = user_data['email']
        self.password_hash = user_data['password']
        self.nombre = user_data.get('nombre', '')
        self.apellido = user_data.get('apellido', '')
        self.telefono = user_data.get('telefono', '')
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def get(user_id):
        try:
            response = supabase.table("usuarios").select("*").eq("id", user_id).execute()
            if response.data:
                return User(response.data[0])
            return None
        except:
            return None
    
    @staticmethod
    def find_by_email(email):
        try:
            response = supabase.table("usuarios").select("*").eq("email", email).execute()
            if response.data:
                return User(response.data[0])
            return None
        except:
            return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# ========== FUNCIONES DE CORREO ==========
def send_reset_email(email, token):
    reset_url = f"https://tecnobots-web-production.up.railway.app/reset-password/{token}"
    
    api_key = os.getenv("BREVO_API_KEY")
    
    data = {
        "sender": {"email": "tecnobotss2021@gmail.com", "name": "TECNOBOTS"},
        "to": [{"email": email}],
        "subject": "Restablecer contraseña - TECNOBOTS",
        "htmlContent": f"""
        <h2>Restablece tu contraseña</h2>
        <p>Haz clic en el siguiente enlace:</p>
        <p><a href="{reset_url}">Restablecer mi contraseña</a></p>
        <p>Este enlace expirará en 1 hora.</p>
        """
    }
    
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=data
        )
        if response.status_code == 201:
            print(f"✅ Correo enviado a {email}")
            return True
        else:
            print(f"❌ Error API: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def send_purchase_email(user_email, user_nombre, cart_items, total, delivery="no"):
    api_key = os.getenv("BREVO_API_KEY")
    
    productos_html = ""
    for item in cart_items.values():
        precio = item['price']
        cantidad = item['quantity']
        subtotal = precio * cantidad
        productos_html += f"""
        <tr>
            <td>{item['name']}</td>
            <td>{cantidad}</td>
            <td>${precio:.2f}</td>
            <td>${subtotal:.2f}</td>
        </tr>
        """
    
    telefono = current_user.telefono if current_user.is_authenticated else 'No registrado'
    
    delivery_texto = "✅ Sí, requiere delivery" if delivery == "si" else "❌ No, retirará en tienda"
    
    html = f"""
    <h2>¡Nueva compra en TECNOBOTS!</h2>
    <p><strong>Cliente:</strong> {user_nombre}</p>
    <p><strong>Email:</strong> {user_email}</p>
    <p><strong>Teléfono:</strong> {telefono}</p>
    <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    <p><strong>Delivery:</strong> {delivery_texto}</p>
    
    <h3>Productos comprados:</h3>
    <table border="1" cellpadding="8" style="border-collapse: collapse;">
        <tr style="background: #1f4e6e; color: white;">
            <th>Producto</th>
            <th>Cantidad</th>
            <th>Precio unitario</th>
            <th>Subtotal</th>
        </tr>
        {productos_html}
        <tr style="background: #f0f0f0; font-weight: bold;">
            <td colspan="3" align="right">TOTAL:</td>
            <td>${total:.2f}</td>
        </tr>
    一
    
    <p><strong>Método de pago:</strong> Por confirmar (el cliente se comunicará)</p>
    """
    
    data = {
        "sender": {"email": "tecnobotss2021@gmail.com", "name": "TECNOBOTS"},
        "to": [{"email": "tecnobotss2021@gmail.com"}, {"email": user_email}],
        "subject": f"Nueva compra - TECNOBOTS - {user_nombre}",
        "htmlContent": html
    }
    
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=data
        )
        return response.status_code == 201
    except Exception as e:
        print(f"Error enviando correo de compra: {e}")
        return False

# ========== FUNCIONES DE FILTRO ==========
def aplicar_filtro_fecha(query, mes, año):
    """Aplica filtro de mes y año a una consulta de Supabase (columna 'fecha')"""
    if mes and mes != 'todos' and año and año != 'todos':
        start_date = f"{año}-{mes.zfill(2)}-01"
        if mes == '12':
            end_date = f"{int(año)+1}-01-01"
        else:
            end_date = f"{año}-{int(mes)+1:02d}-01"
        query = query.gte("fecha", start_date).lt("fecha", end_date)
    elif año and año != 'todos':
        start_date = f"{año}-01-01"
        end_date = f"{int(año)+1}-01-01"
        query = query.gte("fecha", start_date).lt("fecha", end_date)
    return query

def aplicar_filtro_fecha_general(query, mes, año, columna_fecha):
    """Aplica filtro de mes y año a cualquier tabla con columna de fecha específica"""
    if mes and mes != 'todos' and año and año != 'todos':
        start_date = f"{año}-{mes.zfill(2)}-01"
        if mes == '12':
            end_date = f"{int(año)+1}-01-01"
        else:
            end_date = f"{año}-{int(mes)+1:02d}-01"
        query = query.gte(columna_fecha, start_date).lt(columna_fecha, end_date)
    elif año and año != 'todos':
        start_date = f"{año}-01-01"
        end_date = f"{int(año)+1}-01-01"
        query = query.gte(columna_fecha, start_date).lt(columna_fecha, end_date)
    return query

# ========== VENTAS ==========
def guardar_venta_en_historial(user_email, user_nombre, cart_items, total):
    productos_lista = []
    for item in cart_items.values():
        productos_lista.append({
            "nombre": item['name'],
            "cantidad": item['quantity'],
            "precio": item['price'],
            "subtotal": item['price'] * item['quantity']
        })
    
    user = User.find_by_email(user_email)
    telefono = user.telefono if user else 'No registrado'
    
    data = {
        "cliente_nombre": user_nombre,
        "cliente_email": user_email,
        "cliente_telefono": telefono,
        "productos": productos_lista,
        "total": total,
        "estado": "Pendiente"
    }
    
    try:
        supabase.table("ventas_historial").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error guardando venta: {e}")
        return False

def concretar_venta(venta_id):
    response = supabase.table("ventas_historial").select("*").eq("id", venta_id).execute()
    if not response.data:
        return False
    
    venta = response.data[0]
    productos = venta['productos']
    
    for producto in productos:
        prod_response = supabase.table("productos").select("*").eq("nombre", producto['nombre']).execute()
        if prod_response.data:
            prod_id = prod_response.data[0]['id']
            nueva_cantidad = prod_response.data[0]['cantidad'] - producto['cantidad']
            supabase.table("productos").update({"cantidad": nueva_cantidad}).eq("id", prod_id).execute()
    
    supabase.table("ventas").insert({
        "cliente": venta['cliente_nombre'],
        "total": venta['total'],
        "abono": venta['total'],
        "estado": "Completado",
        "fecha_venta": venta['fecha']
    }).execute()
    
    supabase.table("ventas_historial").update({"estado": "Concretada"}).eq("id", venta_id).execute()
    return True

def eliminar_venta_historial(venta_id):
    supabase.table("ventas_historial").delete().eq("id", venta_id).execute()
    return True

# ========== RUTAS PÚBLICAS ==========
@app.route('/')
def index():
    response = supabase.table("productos").select("*").execute()
    productos = response.data if response.data else []
    
    for p in productos:
        res_imgs = supabase.table("productos_imagenes").select("imagen_url").eq("producto_id", p["id"]).order("orden").execute()
        p["imagenes"] = res_imgs.data if res_imgs.data else []
    
    return render_template('index.html', productos=productos)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    response = supabase.table("productos").select("*").ilike("nombre", f"%{query}%").execute()
    return jsonify(response.data if response.data else [])

@app.route('/cart')
def cart():
    cart_items = session.get('cart', {})
    total = sum(item['price'] * item['quantity'] for item in cart_items.values())
    return render_template('cart.html', cart=cart_items, total=total)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    product_name = request.form.get('product_name')
    product_price = float(request.form.get('product_price'))
    
    if 'cart' not in session:
        session['cart'] = {}
    
    cart = session['cart']
    if product_id in cart:
        cart[product_id]['quantity'] += 1
    else:
        cart[product_id] = {
            'name': product_name,
            'price': product_price,
            'quantity': 1
        }
    session['cart'] = cart
    return redirect(url_for('index'))

@app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    product_id = request.form.get('product_id')
    
    if 'cart' in session and product_id in session['cart']:
        del session['cart'][product_id]
        session.modified = True
    
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart_items = session.get('cart', {})
    if not cart_items:
        return redirect(url_for('cart'))
    
    total = sum(item['price'] * item['quantity'] for item in cart_items.values())
    
    # Obtener opción de delivery
    delivery = request.form.get('delivery', 'no')
    
    guardar_venta_en_historial(current_user.email, current_user.nombre, cart_items, total)
    
    if send_purchase_email(current_user.email, current_user.nombre, cart_items, total, delivery):
        session.pop('cart', None)
        return render_template('checkout_success.html', mensaje="✅ ¡Compra realizada! Te hemos enviado un correo con los detalles.")
    else:
        return render_template('checkout_success.html', error="❌ Hubo un error al enviar el correo. Intenta de nuevo.")

# ========== AUTENTICACIÓN CON FLASK-LOGIN ==========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        telefono = request.form.get('telefono')
        
        if User.find_by_email(email):
            return render_template('register.html', error="El correo ya está registrado")
        
        hashed_password = generate_password_hash(password)
        
        try:
            data = {
                "email": email,
                "password": hashed_password,
                "nombre": nombre,
                "apellido": apellido,
                "telefono": telefono
            }
            supabase.table("usuarios").insert(data).execute()
            return redirect(url_for('login'))
        except Exception as e:
            return render_template('register.html', error=str(e))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.find_by_email(email)
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Correo o contraseña incorrectos")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    mes = request.args.get('mes', 'todos')
    año = request.args.get('año', 'todos')
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        telefono = request.form.get('telefono')
        
        try:
            supabase.table("usuarios").update({
                "nombre": nombre,
                "apellido": apellido,
                "telefono": telefono
            }).eq("id", current_user.id).execute()
            
            current_user.nombre = nombre
            current_user.apellido = apellido
            current_user.telefono = telefono
            
            mensaje = "✅ Datos actualizados correctamente"
        except Exception as e:
            mensaje = f"❌ Error: {str(e)}"
    
    query = supabase.table("ventas_historial").select("*").eq("cliente_email", current_user.email)
    query = aplicar_filtro_fecha(query, mes, año)
    response = query.order("fecha", desc=True).execute()
    compras = response.data if response.data else []
    
    años_response = supabase.table("ventas_historial").select("fecha").eq("cliente_email", current_user.email).execute()
    años_disponibles = sorted(set([f['fecha'][:4] for f in años_response.data if f.get('fecha')]), reverse=True) if años_response.data else []
    
    return render_template('perfil.html', user=current_user, compras=compras, 
                          mes_seleccionado=mes, año_seleccionado=año, años_disponibles=años_disponibles)

@app.route('/cambiar-password', methods=['GET', 'POST'])
def cambiar_password():
    global ADMIN_PASS
    
    # Verificar si es ADMIN o USUARIO NORMAL
    is_admin = session.get('admin_logged', False)
    is_user = current_user.is_authenticated
    
    if not is_admin and not is_user:
        # No hay nadie logueado, redirigir según corresponda
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Si es ADMIN
        if is_admin:
            # Verificar contraseña actual del admin
            if current_password != ADMIN_PASS:
                return render_template('cambiar_password.html', error="❌ Contraseña actual incorrecta", is_admin=True)
            
            if new_password != confirm_password:
                return render_template('cambiar_password.html', error="❌ Las contraseñas nuevas no coinciden", is_admin=True)
            
            if len(new_password) < 6:
                return render_template('cambiar_password.html', error="❌ La contraseña debe tener al menos 6 caracteres", is_admin=True)
            
            # Guardar nueva contraseña en Supabase
            if guardar_admin_password(new_password):
                ADMIN_PASS = new_password
                return render_template('cambiar_password.html', success="✅ Contraseña de administrador actualizada correctamente", is_admin=True)
            else:
                return render_template('cambiar_password.html', error="❌ Error al guardar la nueva contraseña", is_admin=True)
        
        # Si es USUARIO NORMAL
        elif is_user:
            if not current_user.check_password(current_password):
                return render_template('cambiar_password.html', error="❌ Contraseña actual incorrecta", is_admin=False)
            
            if new_password != confirm_password:
                return render_template('cambiar_password.html', error="❌ Las contraseñas nuevas no coinciden", is_admin=False)
            
            if len(new_password) < 6:
                return render_template('cambiar_password.html', error="❌ La contraseña debe tener al menos 6 caracteres", is_admin=False)
            
            hashed = generate_password_hash(new_password)
            supabase.table("usuarios").update({"password": hashed}).eq("id", current_user.id).execute()
            
            return render_template('cambiar_password.html', success="✅ Contraseña actualizada correctamente", is_admin=False)
    
    # Mostrar formulario
    return render_template('cambiar_password.html', is_admin=is_admin)

# ========== RECUPERACIÓN DE CONTRASEÑA ==========
@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.find_by_email(email)
        
        if user:
            token = secrets.token_urlsafe(32)
            
            try:
                supabase.table("reset_tokens").insert({
                    "user_id": user.id,
                    "token": token,
                    "expires_at": int(datetime.now().timestamp() + 3600)
                }).execute()
                
                send_reset_email(email, token)
                message = "Se ha enviado un enlace de recuperación a tu correo electrónico."
                return render_template('recuperar.html', message=message)
            except Exception as e:
                return render_template('recuperar.html', error=f"Error: {str(e)}")
        else:
            return render_template('recuperar.html', error="No existe una cuenta con ese correo")
    
    return render_template('recuperar.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        response = supabase.table("reset_tokens").select("*").eq("token", token).execute()
        if not response.data:
            return render_template('reset_password.html', error="Enlace inválido o expirado")
        
        token_data = response.data[0]
        if token_data['expires_at'] < datetime.now().timestamp():
            return render_template('reset_password.html', error="El enlace ha expirado")
        
        user_id = token_data['user_id']
        
        if request.method == 'POST':
            new_password = request.form.get('password')
            confirm = request.form.get('confirm_password')
            
            if new_password != confirm:
                return render_template('reset_password.html', error="Las contraseñas no coinciden")
            if len(new_password) < 6:
                return render_template('reset_password.html', error="Mínimo 6 caracteres")
            
            hashed = generate_password_hash(new_password)
            supabase.table("usuarios").update({"password": hashed}).eq("id", user_id).execute()
            
            supabase.table("reset_tokens").delete().eq("token", token).execute()
            
            return render_template('reset_password.html', success="✅ Contraseña actualizada. Ya puedes iniciar sesión.")
        
        return render_template('reset_password.html', token=token)
    except Exception as e:
        return render_template('reset_password.html', error=str(e))

# ========== ADMINISTRACIÓN ==========
ADMIN_USER = "TECNOBOTS"

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Usuario o contraseña incorrectos"
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_login'))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    response = supabase.table("productos").select("*").order("nombre").execute()
    productos = response.data if response.data else []
    return render_template('admin_dashboard.html', productos=productos)

@app.route('/admin/ventas')
@admin_required
def admin_ventas():
    mes = request.args.get('mes', 'todos')
    año = request.args.get('año', 'todos')
    
    query = supabase.table("ventas_historial").select("*")
    query = aplicar_filtro_fecha(query, mes, año)
    response = query.order("fecha", desc=True).execute()
    ventas = response.data if response.data else []
    
    años_response = supabase.table("ventas_historial").select("fecha").execute()
    años_disponibles = sorted(set([f['fecha'][:4] for f in años_response.data if f.get('fecha')]), reverse=True) if años_response.data else []
    
    return render_template('admin_ventas.html', ventas=ventas, 
                          mes_seleccionado=mes, año_seleccionado=año, años_disponibles=años_disponibles)

@app.route('/admin/venta/concretar/<int:venta_id>')
@admin_required
def admin_venta_concretar(venta_id):
    if concretar_venta(venta_id):
        return redirect(url_for('admin_ventas'))
    else:
        return "Error al concretar la venta", 500

@app.route('/admin/venta/eliminar/<int:venta_id>')
@admin_required
def admin_venta_eliminar(venta_id):
    eliminar_venta_historial(venta_id)
    return redirect(url_for('admin_ventas'))

@app.route('/admin/producto/nuevo', methods=['GET', 'POST'])
@admin_required
def admin_producto_nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio_venta = float(request.form.get('precio_venta'))
        cantidad = int(request.form.get('cantidad'))
        precio_compra = float(request.form.get('precio_compra'))
        porcentaje_envio = float(request.form.get('porcentaje_envio'))
        porcentaje_ganancia = float(request.form.get('porcentaje_ganancia'))
        precio_estimado = precio_compra + (precio_compra * porcentaje_envio / 100) + (precio_compra * porcentaje_ganancia / 100)
        
        data = {
            "nombre": nombre,
            "descripcion": descripcion,
            "precio_venta": precio_venta,
            "cantidad": cantidad,
            "precio_compra": precio_compra,
            "porcentaje_envio": porcentaje_envio,
            "porcentaje_ganancia": porcentaje_ganancia,
            "precio_estimado": precio_estimado
        }
        result = supabase.table("productos").insert(data).execute()
        producto_id = result.data[0]["id"]
        
        # Subir imágenes y videos
        if 'imagenes' in request.files:
            archivos = request.files.getlist('imagenes')
            orden = 0
            for archivo in archivos:
                if archivo.filename != '':
                    ext = archivo.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file_data = archivo.read()
                    supabase.storage.from_('productos').upload(f"productos/{filename}", file_data)
                    url = supabase.storage.from_('productos').get_public_url(f"productos/{filename}")
                    
                    # Detectar si es video
                    es_video = ext in ['mp4', 'webm', 'mov', 'avi', 'mkv']
                    
                    supabase.table("productos_imagenes").insert({
                        "producto_id": producto_id,
                        "imagen_url": url,
                        "orden": orden,
                        "es_video": es_video
                    }).execute()
                    orden += 1
        
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_producto_form.html', producto=None, imagenes=[])


@app.route('/admin/producto/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_producto_editar(id):
    res = supabase.table("productos").select("*").eq("id", id).execute()
    if not res.data:
        return redirect(url_for('admin_dashboard'))
    producto = res.data[0]
    
    res_imagenes = supabase.table("productos_imagenes").select("*").eq("producto_id", id).order("orden").execute()
    imagenes_existentes = res_imagenes.data if res_imagenes.data else []
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio_venta = float(request.form.get('precio_venta'))
        cantidad = int(request.form.get('cantidad'))
        precio_compra = float(request.form.get('precio_compra'))
        porcentaje_envio = float(request.form.get('porcentaje_envio'))
        porcentaje_ganancia = float(request.form.get('porcentaje_ganancia'))
        precio_estimado = precio_compra + (precio_compra * porcentaje_envio / 100) + (precio_compra * porcentaje_ganancia / 100)
        
        update_data = {
            "nombre": nombre,
            "descripcion": descripcion,
            "precio_venta": precio_venta,
            "cantidad": cantidad,
            "precio_compra": precio_compra,
            "porcentaje_envio": porcentaje_envio,
            "porcentaje_ganancia": porcentaje_ganancia,
            "precio_estimado": precio_estimado
        }
        supabase.table("productos").update(update_data).eq("id", id).execute()
        
        # Subir nuevas imágenes y videos
        if 'imagenes' in request.files:
            archivos = request.files.getlist('imagenes')
            orden_actual = len(imagenes_existentes)
            for archivo in archivos:
                if archivo.filename != '':
                    ext = archivo.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file_data = archivo.read()
                    supabase.storage.from_('productos').upload(f"productos/{filename}", file_data)
                    url = supabase.storage.from_('productos').get_public_url(f"productos/{filename}")
                    
                    # Detectar si es video
                    es_video = ext in ['mp4', 'webm', 'mov', 'avi', 'mkv']
                    
                    supabase.table("productos_imagenes").insert({
                        "producto_id": id,
                        "imagen_url": url,
                        "orden": orden_actual,
                        "es_video": es_video
                    }).execute()
                    orden_actual += 1
        
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_producto_form.html', producto=producto, imagenes=imagenes_existentes)


@app.route('/admin/producto/eliminar/<int:id>')
@admin_required
def admin_producto_eliminar(id):
    supabase.table("productos_imagenes").delete().eq("producto_id", id).execute()
    supabase.table("productos").delete().eq("id", id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/imagen/eliminar/<int:id_imagen>')
@admin_required
def admin_imagen_eliminar(id_imagen):
    supabase.table("productos_imagenes").delete().eq("id", id_imagen).execute()
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/resumen')
@admin_required
def admin_resumen():
    # Obtener filtros generales
    mes_general = request.args.get('mes_general', 'todos')
    año_general = request.args.get('año_general', 'todos')
    
    # Obtener filtros individuales
    mes_creditos = request.args.get('mes_creditos', 'todos')
    año_creditos = request.args.get('año_creditos', 'todos')
    mes_ventas = request.args.get('mes_ventas', 'todos')
    año_ventas = request.args.get('año_ventas', 'todos')
    mes_gastos = request.args.get('mes_gastos', 'todos')
    año_gastos = request.args.get('año_gastos', 'todos')
    
    # ========== RESUMEN GENERAL (con filtro general) ==========
    # Mercancía en tienda (sin filtro)
    res_merc = supabase.table("productos").select("cantidad, precio_venta").execute()
    mercancia = sum(p["cantidad"] * p["precio_venta"] for p in res_merc.data) if res_merc.data else 0

    # Ventas para resumen (con filtro general)
    query_ventas_general = supabase.table("ventas").select("*")
    query_ventas_general = aplicar_filtro_fecha_general(query_ventas_general, mes_general, año_general, "fecha_venta")
    res_ventas_general = query_ventas_general.execute()
    ventas_pagadas = sum(v["abono"] for v in res_ventas_general.data) if res_ventas_general.data else 0
    ventas_periodo = sum(v["total"] for v in res_ventas_general.data) if res_ventas_general.data else 0
    
    # Incrementos (con filtro general)
    query_inc = supabase.table("incrementos_efectivo").select("*")
    query_inc = aplicar_filtro_fecha_general(query_inc, mes_general, año_general, "fecha")
    res_inc = query_inc.execute()
    incrementos = sum(i["monto"] for i in res_inc.data) if res_inc.data else 0
    
    # Gastos para resumen (con filtro general)
    query_gastos_general = supabase.table("gastos").select("*")
    query_gastos_general = aplicar_filtro_fecha_general(query_gastos_general, mes_general, año_general, "fecha")
    res_gastos_general = query_gastos_general.execute()
    gastos_general = sum(g["monto"] for g in res_gastos_general.data) if res_gastos_general.data else 0
    
    efectivo = ventas_pagadas + incrementos - gastos_general

    # Créditos para resumen (con filtro general)
    query_creditos_general = supabase.table("ventas").select("*").eq("estado", "Crédito")
    query_creditos_general = aplicar_filtro_fecha_general(query_creditos_general, mes_general, año_general, "fecha_venta")
    res_creditos_general = query_creditos_general.execute()
    creditos_pendientes = 0
    if res_creditos_general.data:
        for v in res_creditos_general.data:
            pendiente = v["total"] - v["abono"]
            if pendiente > 0:
                creditos_pendientes += pendiente

    # ========== MÓDULOS CON FILTROS INDIVIDUALES ==========
    # Ventas a crédito (con filtro individual)
    query_creditos = supabase.table("ventas").select("*").eq("estado", "Crédito")
    query_creditos = aplicar_filtro_fecha_general(query_creditos, mes_creditos, año_creditos, "fecha_venta")
    res_creditos = query_creditos.execute()
    creditos_lista = res_creditos.data if res_creditos.data else []
    
    # Ventas del período (con filtro individual)
    query_ventas = supabase.table("ventas").select("*")
    query_ventas = aplicar_filtro_fecha_general(query_ventas, mes_ventas, año_ventas, "fecha_venta")
    res_ventas = query_ventas.execute()
    ventas_lista = res_ventas.data if res_ventas.data else []
    
    # Gastos (con filtro individual)
    query_gastos = supabase.table("gastos").select("*")
    query_gastos = aplicar_filtro_fecha_general(query_gastos, mes_gastos, año_gastos, "fecha")
    res_gastos = query_gastos.execute()
    gastos_lista = res_gastos.data if res_gastos.data else []
    
    # Almacén (sin filtro)
    res_almacen = supabase.table("registros_almacen").select("cantidad, precio_venta, nombre").eq("estado", "Pendiente").execute()
    total_almacen = sum(a["cantidad"] * a["precio_venta"] for a in res_almacen.data) if res_almacen.data else 0
    almacen_lista = res_almacen.data if res_almacen.data else []
    
    # Productos nuevos (sin filtro)
    res_nuevos = supabase.table("productos_nuevos").select("cantidad, precio_venta, nombre").eq("estado", "Pendiente").execute()
    total_productos_nuevos = sum(n["cantidad"] * n["precio_venta"] for n in res_nuevos.data) if res_nuevos.data else 0
    nuevos_lista = res_nuevos.data if res_nuevos.data else []
    
    # Capital Neto
    capital_neto = efectivo + creditos_pendientes + total_almacen + total_productos_nuevos + mercancia
    
    # Años disponibles para filtros
    años_response = supabase.table("ventas").select("fecha_venta").execute()
    años_disponibles = sorted(set([f['fecha_venta'][:4] for f in años_response.data if f.get('fecha_venta')]), reverse=True) if años_response.data else []
    if not años_disponibles:
        años_disponibles = [datetime.now().strftime('%Y')]
    
    return render_template('admin_resumen.html',
                          mercancia=mercancia,
                          efectivo=efectivo,
                          creditos_pendientes=creditos_pendientes,
                          ventas_periodo=ventas_periodo,
                          capital_neto=capital_neto,
                          # Listas para módulos
                          creditos_lista=creditos_lista[:10],
                          ventas_lista=ventas_lista[:10],
                          gastos_lista=gastos_lista[:10],
                          almacen_lista=almacen_lista[:10],
                          nuevos_lista=nuevos_lista[:10],
                          # Filtros generales
                          mes_general=mes_general,
                          año_general=año_general,
                          # Filtros individuales
                          mes_creditos=mes_creditos,
                          año_creditos=año_creditos,
                          mes_ventas=mes_ventas,
                          año_ventas=año_ventas,
                          mes_gastos=mes_gastos,
                          año_gastos=año_gastos,
                          años_disponibles=años_disponibles)

# ========== EJECUCIÓN ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
