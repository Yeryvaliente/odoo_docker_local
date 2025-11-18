// DEBUG: Verificar configuración de workers

console.log("🔍 DEBUGGING WORKERS CONFIGURATION");
console.log("===================================");

// 1. Verificar configuración del POS
console.log("1. POS Config:");
console.log("   - odoo.pos.config:", odoo?.pos?.config);
console.log("   - workers in config:", odoo?.pos?.config?.workers);

// 2. Verificar session_info
console.log("2. Session Info:");
console.log("   - odoo.session_info:", odoo?.session_info);

// 3. Verificar si hay información del servidor
console.log("3. Server Info:");
console.log("   - server_version_info:", odoo?.session_info?.server_version_info);

// 4. Probar función simple
console.log("4. Simple check result:");
try {
    const simple = odoo.pos.isMultiWorkerSimple();
    console.log("   - isMultiWorkerSimple():", simple);
} catch (error) {
    console.log("   - Error in isMultiWorkerSimple():", error);
}

// 5. Probar función del backend
console.log("5. Backend check result:");
odoo.pos.isMultiWorkerFromBackend().then(result => {
    console.log("   - isMultiWorkerFromBackend():", result);
}).catch(error => {
    console.log("   - Error in isMultiWorkerFromBackend():", error);
});

// 6. Verificar ir.config_parameter directamente
console.log("6. Direct ir.config_parameter check:");
odoo.pos.data.call('ir.config_parameter', 'get_param', ['workers']).then(result => {
    console.log("   - workers from ir.config_parameter:", result);
    console.log("   - parsed:", parseInt(result) || 0);
}).catch(error => {
    console.log("   - Error reading ir.config_parameter:", error);
});

console.log("===================================");
console.log("💡 Si workers = 0 pero config tiene 4, el problema está en:");
console.log("   - Archivo odoo.conf no se está leyendo");
console.log("   - Servicio no se reinició después del cambio");
console.log("   - Configuración se lee desde otro lugar");
