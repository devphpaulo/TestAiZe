import { readFile } from "node:fs/promises";
import { createServer as createHttpServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createInterface } from 'node:readline';
import { WebSocket, WebSocketServer } from "./vendor/ws/wrapper.mjs";
import { HOST, MAX_MESSAGE_BYTES, PORT, ProtocolError, parseClientMessage, } from "./protocol.js";
import { RecorderSession, SessionError } from "./recorder-session.js";
const PUBLIC_DIR = fileURLToPath(new URL("./public/", import.meta.url));
const HOST_STATIC_DIR = fileURLToPath(new URL('../testplayer/static/', import.meta.url));
const MAX_SOCKET_BUFFER_BYTES = 2 * 1024 * 1024;
const ASSETS = new Map([
    ["/", { file: resolve(PUBLIC_DIR, "index.html"), contentType: "text/html; charset=utf-8" }],
    ["/app.js", { file: resolve(PUBLIC_DIR, "app.js"), contentType: "text/javascript; charset=utf-8" }],
    ["/styles.css", { file: resolve(PUBLIC_DIR, "styles.css"), contentType: "text/css; charset=utf-8" }],
    ["/embedded.js", { file: resolve(PUBLIC_DIR, "embedded.js"), contentType: "text/javascript; charset=utf-8" }],
    ['/carbon.css', { file: resolve(HOST_STATIC_DIR, 'carbon.css'), contentType: 'text/css; charset=utf-8' }],
    ['/ui-fixes.css', { file: resolve(HOST_STATIC_DIR, 'ui-fixes.css'), contentType: 'text/css; charset=utf-8' }],
]);
export function createServer(options = {}) {
    const parentOrigin = validateParentOrigin(options.parentOrigin);
    let active;
    let connectionQueue = Promise.resolve();
    let shuttingDown = false;
    const httpServer = createHttpServer((request, response) => {
        const address = httpServer.address();
        if (address && typeof address !== "string" && request.headers.host !== `${HOST}:${address.port}`) {
            response.writeHead(403).end("Forbidden");
            return;
        }
        void serveHttp(request.url ?? "/", request.method ?? "GET", response, parentOrigin);
    });
    const webSockets = new WebSocketServer({ noServer: true, maxPayload: MAX_MESSAGE_BYTES });
    httpServer.on("upgrade", (request, socket, head) => {
        const path = request.url?.split("?", 1)[0];
        if (path !== "/ws") {
            rejectUpgrade(socket, 404, "Not Found");
            return;
        }
        const address = httpServer.address();
        const port = address && typeof address !== "string" ? address.port : PORT;
        const authority = `${HOST}:${port}`;
        if (request.headers.host !== authority || request.headers.origin !== `http://${authority}`) {
            rejectUpgrade(socket, 403, "Forbidden");
            return;
        }
        webSockets.handleUpgrade(request, socket, head, (webSocket) => {
            webSockets.emit("connection", webSocket, request);
        });
    });
    webSockets.on("connection", (socket) => {
        const client = {};
        client.socket = socket;
        client.messages = Promise.resolve();
        client.ready = connectionQueue.then(async () => {
            const previous = active;
            active = undefined;
            if (previous) {
                await previous.session?.close();
                if (previous.socket.readyState === WebSocket.OPEN)
                    previous.socket.close(1012, "Substituída por nova conexão.");
            }
            if (shuttingDown || socket.readyState !== WebSocket.OPEN)
                return;
            client.session = new RecorderSession((message) => send(client, message));
            active = client;
            client.session.publishState();
        });
        connectionQueue = client.ready.catch(() => { });
        socket.on("message", (data, isBinary) => {
            client.messages = client.messages
                .then(async () => {
                await client.ready;
                if (!client.session || client !== active)
                    return;
                if (isBinary)
                    throw new ProtocolError("INVALID_MESSAGE", "Mensagens binárias não são aceitas.");
                const message = parseClientMessage(toBuffer(data));
                await routeMessage(client.session, message);
            })
                .catch((error) => sendError(client, error));
        });
        socket.on("close", () => {
            void client.ready.then(async () => {
                await client.session?.close();
                if (active === client)
                    active = undefined;
            });
        });
        socket.on("error", () => { });
    });
    return {
        httpServer,
        listen: (port = PORT) => new Promise((resolveListen, reject) => {
            const onError = (error) => reject(error);
            httpServer.once("error", onError);
            httpServer.listen(port, HOST, () => {
                httpServer.off("error", onError);
                const address = httpServer.address();
                if (!address || typeof address === "string") {
                    reject(new Error("Servidor não abriu uma porta TCP."));
                    return;
                }
                resolveListen(address.port);
            });
        }),
        close: async () => {
            if (shuttingDown)
                return;
            shuttingDown = true;
            await connectionQueue;
            await active?.session?.close();
            active = undefined;
            for (const socket of webSockets.clients)
                socket.close(1001, "Servidor encerrado.");
            await closeWebSockets(webSockets);
            if (httpServer.listening)
                await new Promise((resolveClose) => httpServer.close(() => resolveClose()));
        },
    };
}
async function routeMessage(session, message) {
    switch (message.type) {
        case "session.start":
            await session.start(message.url);
            return;
        case "session.stop":
            await session.close();
            return;
        case "recording.clear":
            session.clearRecording();
            return;
        default:
            await session.handleInput(message);
    }
}
function send(client, message) {
    if (client.socket.readyState !== WebSocket.OPEN)
        return false;
    if (message.type === "page.frame" && client.socket.bufferedAmount > MAX_SOCKET_BUFFER_BYTES)
        return false;
    try {
        client.socket.send(JSON.stringify(message));
        return true;
    }
    catch {
        return false;
    }
}
function sendError(client, error) {
    if (error instanceof ProtocolError || error instanceof SessionError) {
        send(client, {
            type: "error",
            code: error.code,
            message: error.message,
            recoverable: error instanceof SessionError ? error.recoverable : true,
        });
        return;
    }
    send(client, {
        type: "error",
        code: "BROWSER_FAILED",
        message: "Falha interna ao processar solicitação.",
        recoverable: false,
    });
}
async function serveHttp(requestUrl, method, response, parentOrigin) {
    const path = requestUrl.split("?", 1)[0] ?? "/";
    setSecurityHeaders(response, parentOrigin);
    if (method !== "GET") {
        response.writeHead(404).end("Not Found");
        return;
    }
    if (path === "/health") {
        response.writeHead(200, { "Content-Type": "application/json; charset=utf-8" }).end('{"status":"ok"}');
        return;
    }
    const asset = ASSETS.get(path);
    if (!asset) {
        response.writeHead(404).end("Not Found");
        return;
    }
    try {
        const content = await readFile(asset.file);
        response.writeHead(200, { "Content-Type": asset.contentType }).end(content);
    }
    catch {
        response.writeHead(500).end("Internal Server Error");
    }
}
function setSecurityHeaders(response, parentOrigin) {
    response.setHeader("Content-Security-Policy", `default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self' ws:; base-uri 'none'; frame-ancestors ${parentOrigin ? `'self' ${parentOrigin}` : "'none'"}`);
    response.setHeader("Referrer-Policy", "no-referrer");
    response.setHeader("X-Content-Type-Options", "nosniff");
}
function rejectUpgrade(socket, status, text) {
    socket.end(`HTTP/1.1 ${status} ${text}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
}
function toBuffer(data) {
    if (Buffer.isBuffer(data))
        return data;
    if (Array.isArray(data))
        return Buffer.concat(data);
    return Buffer.from(data);
}
function closeWebSockets(server) {
    return new Promise((resolveClose) => server.close(() => resolveClose()));
}
const entry = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : "";
if (import.meta.url === entry) {
    const recorderServer = createServer({ parentOrigin: process.env.RECORDER_PARENT_ORIGIN });
    const port = Number(process.env.RECORDER_PORT ?? PORT);
    if (!Number.isInteger(port) || port < 0 || port > 65535)
        throw new Error("Porta inválida.");
    recorderServer
        .listen(port)
        .then((port) => console.log(`PLAYWRIGHT_RECORDER_READY http://${HOST}:${port}`))
        .catch(() => {
        console.error("Playwright Recorder não pôde iniciar.");
        process.exitCode = 1;
    });
    let shutdownStarted = false;
    const shutdown = () => {
        if (shutdownStarted) return;
        shutdownStarted = true;
        const deadline = setTimeout(() => process.exit(1), 4000);
        deadline.unref();
        void recorderServer.close().then(() => process.exit(0), () => process.exit(1));
    };
    process.once("SIGINT", shutdown);
    process.once("SIGTERM", shutdown);
    if (process.env.RECORDER_MANAGED === "1") {
        // stdin is the ownership pipe: EOF also cleans up after an abrupt Python exit.
        const managedKeys = new Set();
        const control = createInterface({ input: process.stdin });
        control.on('line', (line) => {
            if (line === 'shutdown') { shutdown(); return; }
            try {
                const message = JSON.parse(line);
                if (message.type !== 'vault.update' || !message.values || typeof message.values !== 'object') return;
                for (const key of managedKeys) delete process.env[key];
                managedKeys.clear();
                for (const [key, value] of Object.entries(message.values)) {
                    if (typeof value !== 'string') continue;
                    process.env[key] = value;
                    managedKeys.add(key);
                }
            } catch { /* Ownership channel errors never log credential values. */ }
        });
        control.once('close', shutdown);
        const parentPid = Number(process.env.RECORDER_PARENT_PID);
        if (Number.isInteger(parentPid) && parentPid > 0) {
            setInterval(() => {
                try {
                    process.kill(parentPid, 0);
                }
                catch {
                    shutdown();
                }
            }, 5000).unref();
        }
    }
}
function validateParentOrigin(value) {
    if (value === undefined)
        return undefined;
    const url = new URL(value);
    if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname) || url.origin !== value) {
        throw new Error("Origem pai inválida.");
    }
    return url.origin;
}
