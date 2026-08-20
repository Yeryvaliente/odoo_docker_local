// Mock UPG unificado y CONMUTABLE EN CALIENTE: hace de UPG para odoo-api y para
// Odoo (twonary_upg). Deja el server corriendo y eliges qué responde UPG antes de
// pulsar "Reprocesar" en Odoo — sin reiniciar node.
//
// Endpoints UPG que atiende (los que usa el flujo de reproceso/riesgo):
//   POST .../charge               -> pre-autorización (devuelve el escenario activo)
//   GET  .../chargeorder/status   -> estado de orden + pago (devuelve el escenario activo)
//   POST .../charge/confirm       -> captura (por defecto AUTHORIZED/CLOSED)
//   POST .../charge/void-preAuth  -> anulación (AUTHORIZATION_VOIDED/VOIDED)
//
// Cada escenario mapea a una rama de _reprocess_decide_and_apply:
//   open_preauth   PRE_AUTHORIZED/OPEN  -> capture+confirm (caso real S1070935)
//   authorized     AUTHORIZED/CLOSED    -> confirm vía checkout
//   risk           PRE_AUTHORIZED/RISK  -> risk_review manual
//   duplicate_risk PRE_AUTHORIZED/DUPLICATE_RISK -> risk_review manual
//   cancelled      CANCELLED/CANCELLED  -> helpdesk (terminal)
//   voided         AUTHORIZATION_VOIDED/VOIDED -> helpdesk (terminal)
//   error_preauth  ERROR_PRE_AUTHORIZE/ERROR_PRE_AUTHORIZE -> helpdesk (terminal)
//   declined       DECLINED/OPEN        -> helpdesk (estado inesperado)
//
// Control (sin reiniciar):
//   GET  http://localhost:9099/                 -> menú + escenario activo
//   GET  http://localhost:9099/_mock/scenario   -> escenario activo (JSON)
//   POST http://localhost:9099/_mock/scenario   -> body {"scenario":"risk"} cambia el activo
//   GET  http://localhost:9099/_mock/set/risk   -> atajo por GET (curl-friendly)
//
// Override por request (no cambia el estado global): ?scenario=risk o header x-mock-scenario.
// La captura (/charge/confirm) se puede forzar a fallar con el escenario capture_fail.
//
// Uso:  MOCK_SCENARIO=authorized node mock_api.js
const http = require('http');

const SCENARIOS = {
  open_preauth: { paymentStatus: 'PRE_AUTHORIZED', chargeOrderStatus: 'OPEN' },
  authorized: { paymentStatus: 'AUTHORIZED', chargeOrderStatus: 'CLOSED' },
  risk: { paymentStatus: 'PRE_AUTHORIZED', chargeOrderStatus: 'RISK' },
  duplicate_risk: { paymentStatus: 'PRE_AUTHORIZED', chargeOrderStatus: 'DUPLICATE_RISK' },
  cancelled: { paymentStatus: 'CANCELLED', chargeOrderStatus: 'CANCELLED' },
  voided: { paymentStatus: 'AUTHORIZATION_VOIDED', chargeOrderStatus: 'VOIDED' },
  error_preauth: { paymentStatus: 'ERROR_PRE_AUTHORIZE', chargeOrderStatus: 'ERROR_PRE_AUTHORIZE' },
  declined: { paymentStatus: 'DECLINED', chargeOrderStatus: 'OPEN' },
  // Fuerza que la captura del hold falle (confirm NO devuelve AUTHORIZED):
  capture_fail: { paymentStatus: 'PRE_AUTHORIZED', chargeOrderStatus: 'OPEN', confirmStatus: 'DECLINED' },
};

const port = process.env.MOCK_PORT || 9099;
let activeScenario = process.env.MOCK_SCENARIO || 'open_preauth';
if (!SCENARIOS[activeScenario]) {
  console.warn(`[mock-upg] MOCK_SCENARIO desconocido "${activeScenario}", usando open_preauth`);
  activeScenario = 'open_preauth';
}

function upgBody(originOrderId, paymentStatus, chargeOrderStatus, amount, currency) {
  return {
    code: 0,
    description: 'OK',
    data: {
      data: {
        originOrderId: originOrderId,
        paymentGateway: 'BRAINTREE CreditCard',
        paymentType: 'NONCE',
        maskedNumber: '548901******2986',
        transactionId: 'MOCK-TXN',
        status: paymentStatus, // estado de PAGO
        chargeOrderId: 990001, // numérico (Odoo lo castea a int)
        chargeOrderStatus: chargeOrderStatus, // estado de ORDEN
        totalPrice: amount,
        totalUsdAmount: amount,
        currency: currency,
        toSelectedMethod: amount,
        secured3D: true,
        key: 'MOCK-' + originOrderId,
        paymentDetails: [],
      },
    },
  };
}

function resolveScenarioKey(requestUrl, requestHeaders) {
  const requestedScenario =
    requestUrl.searchParams.get('scenario') || requestHeaders['x-mock-scenario'];
  if (requestedScenario && SCENARIOS[requestedScenario]) {
    return requestedScenario;
  }
  return activeScenario;
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(payload, null, 2));
}

function scenarioSummary() {
  return {
    active: activeScenario,
    values: SCENARIOS[activeScenario],
    available: Object.keys(SCENARIOS),
  };
}

function handleControl(req, res, requestUrl) {
  // GET / -> menú legible
  if (req.method === 'GET' && requestUrl.pathname === '/') {
    const menu = Object.entries(SCENARIOS)
      .map(([key, value]) => {
        const marker = key === activeScenario ? '>>' : '  ';
        return `${marker} ${key.padEnd(15)} status=${value.paymentStatus} / chargeOrderStatus=${value.chargeOrderStatus}`;
      })
      .join('\n');
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(
      `mock-upg activo en :${port}\n\nEscenario activo: ${activeScenario}\n\n${menu}\n\n` +
        `Cambiar:  curl -X POST localhost:${port}/_mock/scenario -d '{"scenario":"risk"}'\n` +
        `Atajo:    curl localhost:${port}/_mock/set/risk\n`,
    );
    return true;
  }
  // GET /_mock/scenario -> estado actual
  if (req.method === 'GET' && requestUrl.pathname === '/_mock/scenario') {
    sendJson(res, 200, scenarioSummary());
    return true;
  }
  // GET /_mock/set/<key> -> atajo curl-friendly
  if (req.method === 'GET' && requestUrl.pathname.startsWith('/_mock/set/')) {
    const requestedScenario = requestUrl.pathname.slice('/_mock/set/'.length);
    if (!SCENARIOS[requestedScenario]) {
      sendJson(res, 400, { error: 'unknown scenario', available: Object.keys(SCENARIOS) });
      return true;
    }
    activeScenario = requestedScenario;
    console.log(`[mock-upg] escenario -> ${activeScenario}`);
    sendJson(res, 200, scenarioSummary());
    return true;
  }
  return false;
}

const server = http.createServer((req, res) => {
  let rawBody = '';
  req.on('data', (chunk) => (rawBody += chunk));
  req.on('end', () => {
    const requestUrl = new URL(req.url, 'http://localhost');

    // POST /_mock/scenario -> cambia el escenario activo
    if (req.method === 'POST' && requestUrl.pathname === '/_mock/scenario') {
      let requestedScenario;
      try {
        requestedScenario = JSON.parse(rawBody || '{}').scenario;
      } catch (parseError) {
        requestedScenario = undefined;
      }
      if (!SCENARIOS[requestedScenario]) {
        sendJson(res, 400, { error: 'unknown scenario', available: Object.keys(SCENARIOS) });
        return;
      }
      activeScenario = requestedScenario;
      console.log(`[mock-upg] escenario -> ${activeScenario}`);
      sendJson(res, 200, scenarioSummary());
      return;
    }

    if (handleControl(req, res, requestUrl)) {
      return;
    }

    // --- Endpoints UPG ---
    let parsedBody = {};
    try {
      parsedBody = JSON.parse(rawBody || '{}');
    } catch (parseError) {
      parsedBody = {};
    }
    const originOrderId =
      requestUrl.searchParams.get('originOrderId') || parsedBody.originOrderId || 'UNKNOWN';
    const amount = parsedBody.amount != null ? parsedBody.amount : 1.0;
    const currency = parsedBody.currency || 'USD';

    const scenarioKey = resolveScenarioKey(requestUrl, req.headers);
    const scenario = SCENARIOS[scenarioKey];

    let payload;
    let tag;
    if (req.url.includes('/charge/confirm')) {
      // Captura del hold. Por defecto AUTHORIZED/CLOSED (para que PRE_AUTHORIZED
      // -> capture+confirm complete). El escenario capture_fail lo fuerza a fallar.
      const confirmStatus = scenario.confirmStatus || 'AUTHORIZED';
      const confirmOrderStatus = confirmStatus === 'AUTHORIZED' ? 'CLOSED' : scenario.chargeOrderStatus;
      payload = upgBody(originOrderId, confirmStatus, confirmOrderStatus, amount, currency);
      tag = `CONFIRM(capture) -> ${confirmStatus}/${confirmOrderStatus} [${scenarioKey}]`;
    } else if (req.url.includes('/void-preAuth')) {
      payload = upgBody(originOrderId, 'AUTHORIZATION_VOIDED', 'VOIDED', amount, currency);
      tag = 'VOID -> AUTHORIZATION_VOIDED/VOIDED';
    } else if (req.url.includes('/chargeorder/status')) {
      payload = upgBody(originOrderId, scenario.paymentStatus, scenario.chargeOrderStatus, amount, currency);
      tag = `STATUS -> ${scenario.paymentStatus}/${scenario.chargeOrderStatus} [${scenarioKey}]`;
    } else {
      // POST .../charge  (pre-auth)
      payload = upgBody(originOrderId, scenario.paymentStatus, scenario.chargeOrderStatus, amount, currency);
      tag = `CHARGE(pre-auth) -> ${scenario.paymentStatus}/${scenario.chargeOrderStatus} [${scenarioKey}]`;
    }
    console.log(`[mock-upg] ${req.method} ${req.url}  | order=${originOrderId} | ${tag}`);
    sendJson(res, 200, payload);
  });
});

server.listen(port, () =>
  console.log(
    `[mock-upg] UP en http://localhost:${port}  (escenario activo=${activeScenario})\n` +
      `           menú: curl localhost:${port}/   ·   cambiar: curl localhost:${port}/_mock/set/<escenario>`,
  ),
);
