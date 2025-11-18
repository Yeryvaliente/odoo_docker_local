// FORMAS MÁS SENCILLAS DE DETECTAR MULTI-WORKER EN ODOO POS

// 1. VERIFICACIÓN MÁS SIMPLE - Configuración
function isMultiWorkerSimple() {
    return parseInt(odoo.pos.config.workers) > 0;
}

// 2. VERIFICACIÓN EN CÓDIGO
if (odoo.pos.isMultiWorker) {
    console.log("MULTI-WORKER: Necesitas sincronizar direcciones");
    // Tu código de sincronización aquí
} else {
    console.log("SINGLE-WORKER: No necesitas sincronizar");
}

// 3. PRUEBA RÁPIDA EN CONSOLA DEL NAVEGADOR
// Abre F12 -> Console y ejecuta:
isMultiWorkerSimple()  // true/false
odoo.pos.isMultiWorker  // true/false

// 4. VERIFICACIÓN MANUAL
// Revisa tu odoo.conf:
// workers = 4  // Si > 0, es multi-worker
// workers = 0  // Single worker

console.log("Workers configurados:", odoo.pos.config.workers);
