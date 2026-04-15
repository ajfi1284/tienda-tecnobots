$(document).ready(function() {
    // Búsqueda en tiempo real
    $('#search-input').on('keyup', function() {
        let query = $(this).val();
        if (query.length > 0) {
            $.ajax({
                url: '/search?q=' + query,
                method: 'GET',
                success: function(data) {
                    renderProducts(data);
                }
            });
        } else {
            location.reload();
        }
    });

    function renderProducts(productos) {
        let html = '';
        productos.forEach(p => {
            let imagen = p.imagen_url ? p.imagen_url : '/static/images/placeholder.png';
            html += `
                <div class="product-card">
                    <div class="product-image">
                        <img src="${imagen}" alt="${p.nombre}">
                    </div>
                    <h3>${p.nombre}</h3>
                    <p class="price">$${p.precio_venta.toFixed(2)}</p>
                    <p class="stock">Stock: ${p.cantidad}</p>
                    <form method="POST" action="/add_to_cart">
                        <input type="hidden" name="product_id" value="${p.nombre}">
                        <input type="hidden" name="product_name" value="${p.nombre}">
                        <input type="hidden" name="product_price" value="${p.precio_venta}">
                        <button type="submit" class="btn-add">Agregar al carrito</button>
                    </form>
                </div>
            `;
        });
        $('#products-grid').html(html);
    }
});