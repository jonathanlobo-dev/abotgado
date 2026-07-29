// Service Worker de aBOTgado — cachea SOLO el shell estático de la UI.
// CRÍTICO: nunca cachea llamadas a la API (respuestas legales). Servir una
// respuesta legal vieja desde caché sería peligroso (leyes/planes cambian).
// La API vive en otro origen (railway.app) y ni siquiera pasa por este SW,
// pero además se excluye explícitamente por seguridad.

const CACHE_VERSION = "abotgado-shell-v1";
const SHELL_FILES = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Solo GET, solo mismo origen (el shell). Todo lo demás (API en otro
  // dominio, POST/PUT/DELETE) pasa directo a la red sin tocar el caché.
  if (req.method !== "GET" || url.origin !== self.location.origin) {
    return; // no respondWith → comportamiento normal de red
  }

  // Nunca cachear rutas de API aunque algún día compartan origen.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/consultar")) {
    return;
  }

  // Shell: cache-first con actualización en segundo plano (stale-while-revalidate).
  event.respondWith(
    caches.match(req).then((cached) => {
      const fetchPromise = fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const clone = res.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(req, clone));
          }
          return res;
        })
        .catch(() => cached); // sin red → lo que haya en caché

      return cached || fetchPromise;
    })
  );
});
