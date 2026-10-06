export const HOST = "127.0.0.1";
export const PORT = 4173;
export const VIEWPORT = { width: 1280, height: 720 };
export const MAX_MESSAGE_BYTES = 64 * 1024;
const MAX_URL_LENGTH = 4096;
const MAX_TEXT_LENGTH = 32 * 1024;
const MAX_SCRIPT_LENGTH = 64 * 1024;
const MAX_KEY_LENGTH = 128;
const MAX_WHEEL_DELTA = 10_000;
export class ProtocolError extends Error {
    code;
    constructor(code, message) {
        super(message);
        this.name = "ProtocolError";
        this.code = code;
    }
}
export function validateTargetUrl(value) {
    if (typeof value !== "string" || value.length < 1 || value.length > MAX_URL_LENGTH)
        throw new ProtocolError("INVALID_URL", "Informe uma URL HTTP ou HTTPS válida.");
    try {
        const url = new URL(value);
        if (url.protocol !== "http:" && url.protocol !== "https:")
            throw new ProtocolError("INVALID_URL", "Somente URLs HTTP e HTTPS são permitidas.");
        return url.href;
    }
    catch (error) {
        if (error instanceof ProtocolError)
            throw error;
        throw new ProtocolError("INVALID_URL", "Informe uma URL HTTP ou HTTPS válida.");
    }
}
export function parseClientMessage(raw) {
    if (Buffer.byteLength(raw) > MAX_MESSAGE_BYTES)
        throw invalid("Mensagem excede o limite de 64 KiB.");
    let value;
    try {
        value = JSON.parse(raw.toString());
    }
    catch {
        throw invalid("Mensagem JSON inválida.");
    }
    if (!isRecord(value) || typeof value.type !== "string")
        throw invalid("Mensagem deve possuir um tipo válido.");
    switch (value.type) {
        case "session.start":
            return { type: value.type, url: validateTargetUrl(value.url) };
        case "session.stop":
        case "recording.clear":
        case "input.hover.clear":
            return { type: value.type };
        case "input.pointer":
            return parsePointer(value);
        case "input.wheel":
            return parseWheel(value);
        case "input.key":
            return parseKey(value);
        case "input.text":
            if (typeof value.text !== "string" || value.text.length > MAX_TEXT_LENGTH)
                throw invalid("Texto inválido.");
            return { type: value.type, text: value.text };
        case "script.run":
            if (typeof value.steps !== "string" || !value.steps.trim() || value.steps.length > MAX_SCRIPT_LENGTH)
                throw invalid("Script inválido.");
            return { type: value.type, steps: value.steps };
        case "input.select":
            if (!Number.isSafeInteger(value.selectId) || !inRange(value.selectId, 1, Number.MAX_SAFE_INTEGER))
                throw invalid("Identificador de select inválido.");
            if (value.index !== null && (!Number.isInteger(value.index) || !inRange(value.index, 0, 199)))
                throw invalid("Opção de select inválida.");
            return { type: value.type, selectId: value.selectId, index: value.index };
        default:
            throw invalid("Tipo de mensagem desconhecido.");
    }
}
function parsePointer(value) {
    if (!isOneOf(value.phase, ["move", "down", "up"]))
        throw invalid("Fase de pointer inválida.");
    if (!inRange(value.x, 0, VIEWPORT.width) || !inRange(value.y, 0, VIEWPORT.height))
        throw invalid("Coordenadas fora do viewport.");
    if (value.button !== undefined && !isOneOf(value.button, ["left", "middle", "right"]))
        throw invalid("Botão de pointer inválido.");
    if (value.clickCount !== undefined &&
        (!Number.isInteger(value.clickCount) || !inRange(value.clickCount, 1, 3)))
        throw invalid("Contagem de cliques inválida.");
    return {
        type: "input.pointer",
        phase: value.phase,
        x: value.x,
        y: value.y,
        ...(value.button === undefined ? {} : { button: value.button }),
        ...(value.clickCount === undefined ? {} : { clickCount: value.clickCount }),
    };
}
function parseWheel(value) {
    if (!inRange(value.deltaX, -MAX_WHEEL_DELTA, MAX_WHEEL_DELTA))
        throw invalid("Delta horizontal inválido.");
    if (!inRange(value.deltaY, -MAX_WHEEL_DELTA, MAX_WHEEL_DELTA))
        throw invalid("Delta vertical inválido.");
    return { type: "input.wheel", deltaX: value.deltaX, deltaY: value.deltaY };
}
function parseKey(value) {
    if (!isOneOf(value.phase, ["down", "up"]))
        throw invalid("Fase de tecla inválida.");
    if (!validString(value.key, 1, MAX_KEY_LENGTH))
        throw invalid("Tecla inválida.");
    if (value.code !== undefined && !validString(value.code, 1, MAX_KEY_LENGTH))
        throw invalid("Código de tecla inválido.");
    let modifiers;
    if (value.modifiers !== undefined) {
        if (!Array.isArray(value.modifiers) ||
            value.modifiers.length > 4 ||
            !value.modifiers.every((item) => isOneOf(item, ["Alt", "Control", "Meta", "Shift"])) ||
            new Set(value.modifiers).size !== value.modifiers.length)
            throw invalid("Modificadores inválidos.");
        modifiers = value.modifiers;
    }
    return {
        type: "input.key",
        phase: value.phase,
        key: value.key,
        ...(value.code === undefined ? {} : { code: value.code }),
        ...(modifiers === undefined ? {} : { modifiers }),
    };
}
function invalid(message) {
    return new ProtocolError("INVALID_MESSAGE", message);
}
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function validString(value, min, max) {
    return typeof value === "string" && value.length >= min && value.length <= max;
}
function inRange(value, min, max) {
    return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}
function isOneOf(value, options) {
    return typeof value === "string" && options.includes(value);
}
