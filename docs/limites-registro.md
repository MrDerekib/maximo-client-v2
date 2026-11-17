# Límite del Resumen de Registro

Comprobado en el DOM real de Maximo el 16/11/2026, leyendo una entrada existente
sin modificarla: Registro → Resumen tiene `maxlength="100"`.

MD limita el editor del resumen a ese tamaño y valida todos los resúmenes antes
de abrir una sesión para ejecutar una reparación. El texto de incidencia también
se valida después de añadir `inc: `; el prefijo forma parte del límite.

Detalles conserva su editor de texto extenso. No se recorta ni se mueve texto
entre campos automáticamente. Si ya existe un borrador demasiado largo, se conserva
y se impide ejecutar hasta que el usuario lo corrija. La escritura en Maximo sigue
comprobando además el maxlength del control real por si cambia su configuración.
