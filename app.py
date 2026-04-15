import os
import requests
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = 'clave-super-secreta-para-sesion-cambiar-despues'

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# ========== RUTAS PÚBLICAS ==========

@app.route('/')
def index():
    """Página principal: catálogo de productos (solo stock > 0) con sus imágenes"""
    response = supabase.table("productos").select("*").gt("cantidad", 0).execute()
    productos = response.data if response.data else []
    
    # Cargar imágenes para cada producto
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

# ========== AUTENTICACIÓN DE USUARIOS (Supabase Auth) ==========

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        telefono = request.form.get('telefono')
        
        try:
            # Registrar usuario en Supabase Auth
            user = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            
            # Actualizar el perfil con los datos adicionales
            if user.user:
                supabase.table("profiles").update({
                    "nombre": nombre,
                    "apellido": apellido,
                    "telefono": telefono
                }).eq("id", user.user.id).execute()
            
            return redirect(url_for('login'))
        except Exception as e:
            error = str(e)
            return render_template('register.html', error=error)
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        print(f"Intentando login con: {email}")
        
        try:
            # Método correcto para la versión actual de Supabase
            user = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            print("✅ Login exitoso:", user.user.id)
            session['user'] = user.user.id
            session['user_email'] = user.user.email
            return redirect(url_for('index'))
        except Exception as e:
            print("❌ ERROR en login:", e)
            error = str(e)
            return render_template('login.html', error=error)
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    supabase.auth.sign_out()
    session.pop('user', None)
    session.pop('user_email', None)
    return redirect(url_for('index'))

@app.route('/perfil')
def perfil():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Obtener datos del perfil desde Supabase
    res = supabase.table("profiles").select("*").eq("id", session['user']).execute()
    perfil = res.data[0] if res.data else {}
    return render_template('perfil.html', perfil=perfil, email=session.get('user_email'))

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        email = request.form.get('email')
        try:
            # Supabase envía un correo de recuperación
            supabase.auth.reset_password_for_email(email, options={"redirect_to": "https://tecnobots-web-production.up.railway.app/reset-password"})
            message = "Se ha enviado un enlace de recuperación a tu correo electrónico."
            return render_template('recuperar.html', message=message)
        except Exception as e:
            error = str(e)
            return render_template('recuperar.html', error=error)
    return render_template('recuperar.html')

# ========== ADMINISTRACIÓN (protegido) ==========
ADMIN_USER = "TECNOBOTS"
ADMIN_PASS = "TECNO2024"

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

@app.route('/admin/producto/nuevo', methods=['GET', 'POST'])
@admin_required
def admin_producto_nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        precio_venta = float(request.form.get('precio_venta'))
        cantidad = int(request.form.get('cantidad'))
        precio_compra = float(request.form.get('precio_compra'))
        porcentaje_envio = float(request.form.get('porcentaje_envio'))
        porcentaje_ganancia = float(request.form.get('porcentaje_ganancia'))
        precio_estimado = precio_compra + (precio_compra * porcentaje_envio / 100) + (precio_compra * porcentaje_ganancia / 100)
        
        data = {
            "nombre": nombre,
            "precio_venta": precio_venta,
            "cantidad": cantidad,
            "precio_compra": precio_compra,
            "porcentaje_envio": porcentaje_envio,
            "porcentaje_ganancia": porcentaje_ganancia,
            "precio_estimado": precio_estimado
        }
        result = supabase.table("productos").insert(data).execute()
        producto_id = result.data[0]["id"]
        
        if 'imagenes' in request.files:
            archivos = request.files.getlist('imagenes')
            orden = 0
            for archivo in archivos:
                if archivo.filename != '':
                    ext = archivo.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file_data = archivo.read()
                    supabase.storage.from_('productos').upload(f"productos/{filename}", file_data)
                    imagen_url = supabase.storage.from_('productos').get_public_url(f"productos/{filename}")
                    
                    supabase.table("productos_imagenes").insert({
                        "producto_id": producto_id,
                        "imagen_url": imagen_url,
                        "orden": orden
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
        precio_venta = float(request.form.get('precio_venta'))
        cantidad = int(request.form.get('cantidad'))
        precio_compra = float(request.form.get('precio_compra'))
        porcentaje_envio = float(request.form.get('porcentaje_envio'))
        porcentaje_ganancia = float(request.form.get('porcentaje_ganancia'))
        precio_estimado = precio_compra + (precio_compra * porcentaje_envio / 100) + (precio_compra * porcentaje_ganancia / 100)
        
        update_data = {
            "nombre": nombre,
            "precio_venta": precio_venta,
            "cantidad": cantidad,
            "precio_compra": precio_compra,
            "porcentaje_envio": porcentaje_envio,
            "porcentaje_ganancia": porcentaje_ganancia,
            "precio_estimado": precio_estimado
        }
        supabase.table("productos").update(update_data).eq("id", id).execute()
        
        if 'imagenes' in request.files:
            archivos = request.files.getlist('imagenes')
            orden_actual = len(imagenes_existentes)
            for archivo in archivos:
                if archivo.filename != '':
                    ext = archivo.filename.rsplit('.', 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file_data = archivo.read()
                    supabase.storage.from_('productos').upload(f"productos/{filename}", file_data)
                    imagen_url = supabase.storage.from_('productos').get_public_url(f"productos/{filename}")
                    
                    supabase.table("productos_imagenes").insert({
                        "producto_id": id,
                        "imagen_url": imagen_url,
                        "orden": orden_actual
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
    res_merc = supabase.table("productos").select("cantidad, precio_venta").execute()
    mercancia = sum(p["cantidad"] * p["precio_venta"] for p in res_merc.data) if res_merc.data else 0

    res_ventas = supabase.table("ventas").select("abono").execute()
    ventas_pagadas = sum(v["abono"] for v in res_ventas.data) if res_ventas.data else 0
    res_inc = supabase.table("incrementos_efectivo").select("monto").execute()
    incrementos = sum(i["monto"] for i in res_inc.data) if res_inc.data else 0
    res_gastos = supabase.table("gastos").select("monto").execute()
    gastos = sum(g["monto"] for g in res_gastos.data) if res_gastos.data else 0
    efectivo = ventas_pagadas + incrementos - gastos

    res_almacen = supabase.table("registros_almacen").select("cantidad, precio_venta").eq("estado", "Pendiente").execute()
    total_almacen = sum(a["cantidad"] * a["precio_venta"] for a in res_almacen.data) if res_almacen.data else 0

    res_nuevos = supabase.table("productos_nuevos").select("cantidad, precio_venta").eq("estado", "Pendiente").execute()
    total_productos_nuevos = sum(n["cantidad"] * n["precio_venta"] for n in res_nuevos.data) if res_nuevos.data else 0

    res_creditos = supabase.table("ventas").select("total, abono").eq("estado", "Crédito").execute()
    creditos_pendientes = 0
    if res_creditos.data:
        for v in res_creditos.data:
            if v["abono"] < v["total"]:
                creditos_pendientes += v["total"] - v["abono"]

    hoy = datetime.now().strftime('%Y-%m-%d')
    res_hoy = supabase.table("ventas").select("total").gte("fecha_venta", hoy).lte("fecha_venta", hoy + " 23:59:59").execute()
    ventas_hoy = sum(v["total"] for v in res_hoy.data) if res_hoy.data else 0

    mes_actual = datetime.now().strftime('%Y-%m')
    res_mes = supabase.table("ventas").select("total").gte("fecha_venta", mes_actual + "-01").execute()
    ventas_mes = sum(v["total"] for v in res_mes.data) if res_mes.data else 0

    res_ultimas_ventas = supabase.table("ventas").select("*").order("fecha_venta", desc=True).limit(10).execute()
    ultimas_ventas = res_ultimas_ventas.data if res_ultimas_ventas.data else []

    res_ultimos_gastos = supabase.table("gastos").select("*").order("fecha", desc=True).limit(10).execute()
    ultimos_gastos = res_ultimos_gastos.data if res_ultimos_gastos.data else []

    return render_template('admin_resumen.html',
                          mercancia=mercancia,
                          efectivo=efectivo,
                          creditos_pendientes=creditos_pendientes,
                          ventas_hoy=ventas_hoy,
                          ventas_mes=ventas_mes,
                          total_almacen=total_almacen,
                          total_productos_nuevos=total_productos_nuevos,
                          ultimas_ventas=ultimas_ventas,
                          ultimos_gastos=ultimos_gastos)

# ========== EJECUCIÓN ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
