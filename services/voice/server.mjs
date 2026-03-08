import http from "node:http";
import { Buffer } from "node:buffer";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import {
  BedrockRuntimeClient,
  InvokeModelWithBidirectionalStreamCommand,
} from "@aws-sdk/client-bedrock-runtime";

function loadDotEnvIfPresent() {
  const candidates = [
    path.resolve(process.cwd(), ".env"),
    path.resolve(process.cwd(), "..", ".env"),
    path.resolve(process.cwd(), "..", "..", ".env"),
  ];
  for (const p of candidates) {
    if (!fs.existsSync(p)) continue;
    try {
      const raw = fs.readFileSync(p, "utf-8");
      for (const line of raw.split(/\r?\n/)) {
        const s = String(line || "").trim();
        if (!s || s.startsWith("#")) continue;
        const idx = s.indexOf("=");
        if (idx <= 0) continue;
        const key = s.slice(0, idx).trim();
        let value = s.slice(idx + 1).trim();
        if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }
        if (key && !(key in process.env)) {
          process.env[key] = value;
        }
      }
      return;
    } catch {
      // Ignore and continue with next candidate.
    }
  }
}

loadDotEnvIfPresent();

const REGION = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1";
const MODEL_ID = process.env.NOVA_SONIC_MODEL_ID || "";
const PORT = Number.parseInt(process.env.PORT || "8001", 10);
const DEFAULT_SONIC_MODEL_ID = "amazon.nova-sonic-v1:0";

function json(res, statusCode, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type",
  });
  res.end(body);
}

function wavFromPcm16({ pcm16, sampleRateHertz = 16000, channelCount = 1 }) {
  // Minimal RIFF/WAVE header for PCM16LE.
  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const byteRate = sampleRateHertz * blockAlign;

  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + pcm16.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16); // PCM header size
  header.writeUInt16LE(1, 20); // format=PCM
  header.writeUInt16LE(channelCount, 22);
  header.writeUInt32LE(sampleRateHertz, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(16, 34); // bits per sample
  header.write("data", 36);
  header.writeUInt32LE(pcm16.length, 40);
  return Buffer.concat([header, pcm16]);
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf-8");
  if (!raw.trim()) return {};
  return JSON.parse(raw);
}

function chunkBase64(b64, chunkBytes = 12_000) {
  const buf = Buffer.from(b64, "base64");
  const out = [];
  for (let i = 0; i < buf.length; i += chunkBytes) {
    out.push(buf.subarray(i, Math.min(i + chunkBytes, buf.length)).toString("base64"));
  }
  return out;
}

function eventChunk(eventObj) {
  return { chunk: { bytes: Buffer.from(JSON.stringify({ event: eventObj }), "utf-8") } };
}

function errorDetails(err) {
  const out = {
    name: err?.name || null,
    code: err?.code || null,
    message: err?.message || String(err),
    metadata: err?.$metadata || null,
  };
  if (err?.cause) {
    out.cause = {
      name: err.cause?.name || null,
      code: err.cause?.code || null,
      message: err.cause?.message || String(err.cause),
      metadata: err.cause?.$metadata || null,
    };
  }
  return out;
}

function sonicModelCandidates() {
  const out = [];
  const add = (v) => {
    const s = String(v || "").trim();
    if (!s) return;
    if (!out.includes(s)) out.push(s);
  };
  add(MODEL_ID);
  if (String(MODEL_ID || "").trim() === "amazon.nova-2-sonic-v1:0") {
    add(DEFAULT_SONIC_MODEL_ID);
  }
  add(DEFAULT_SONIC_MODEL_ID);
  return out;
}

function isRetryableSonicError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  return msg.includes("http/2 stream is abnormally aborted");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function sonicRoundTrip({
  audioPcm16Base64,
  sampleRateHertz = 16000,
  systemText = "You are LeakSentinel. Respond briefly with what happened and what to do next.",
  userText = "",
}) {
  const promptName = `ls-${crypto.randomUUID()}`;
  const systemContentName = `system-${crypto.randomUUID()}`;
  const userAudioContentName = `user-audio-${crypto.randomUUID()}`;
  const outputSampleRateHertz = 24000;

  async function* inputEvents() {
    yield eventChunk({
      sessionStart: {
        inferenceConfiguration: {
          maxTokens: 512,
          topP: 0.9,
          temperature: 0.2,
        },
      },
    });

    yield eventChunk({
      promptStart: {
        promptName,
        textOutputConfiguration: { mediaType: "text/plain" },
        audioOutputConfiguration: {
          mediaType: "audio/lpcm",
          sampleRateHertz: outputSampleRateHertz,
          sampleSizeBits: 16,
          channelCount: 1,
          voiceId: "matthew",
        },
      },
    });

    const cleanSystem = String(systemText || "").trim();
    yield eventChunk({
      contentStart: {
        promptName,
        contentName: systemContentName,
        type: "TEXT",
        role: "SYSTEM",
        interactive: false,
        textInputConfiguration: { mediaType: "text/plain" },
      },
    });
    yield eventChunk({
      textInput: {
        promptName,
        contentName: systemContentName,
        content: cleanSystem || "You are LeakSentinel. Be concise and action-oriented.",
      },
    });
    yield eventChunk({
      contentEnd: {
        promptName,
        contentName: systemContentName,
      },
    });
    void userText;

    yield eventChunk({
      contentStart: {
        promptName,
        contentName: userAudioContentName,
        type: "AUDIO",
        role: "USER",
        interactive: true,
        audioInputConfiguration: {
          mediaType: "audio/lpcm",
          sampleRateHertz,
          sampleSizeBits: 16,
          channelCount: 1,
          audioType: "SPEECH",
        },
      },
    });

    for (const b64 of chunkBase64(audioPcm16Base64, 3_200)) {
      yield eventChunk({
        audioInput: {
          promptName,
          contentName: userAudioContentName,
          content: b64,
        },
      });
      await sleep(5);
    }

    yield eventChunk({
      contentEnd: {
        promptName,
        contentName: userAudioContentName,
      },
    });
    yield eventChunk({ promptEnd: { promptName } });
    yield eventChunk({ sessionEnd: {} });
  }

  const modelCandidates = sonicModelCandidates();
  let lastError = null;
  const attemptErrors = [];
  const maxAttemptsPerModel = 2;

  for (const modelId of modelCandidates) {
    for (let attempt = 1; attempt <= maxAttemptsPerModel; attempt += 1) {
      try {
        const client = new BedrockRuntimeClient({ region: REGION });
        const cmd = new InvokeModelWithBidirectionalStreamCommand({
          modelId,
          body: inputEvents(),
        });
        const resp = await client.send(cmd);

        const textByContentId = new Map();
        const contentMetaById = new Map();
        const contentOrder = [];
        const audioChunks = [];
        let responseAudioRate = outputSampleRateHertz;

        for await (const ev of resp.body) {
          if (ev?.validationException) {
            throw new Error(`Sonic validationException: ${ev.validationException.message || "unknown"}`);
          }
          if (ev?.modelStreamErrorException) {
            throw new Error(`Sonic modelStreamErrorException: ${ev.modelStreamErrorException.message || "unknown"}`);
          }
          if (ev?.internalServerException) {
            throw new Error(`Sonic internalServerException: ${ev.internalServerException.message || "unknown"}`);
          }
          if (ev?.modelTimeoutException) {
            throw new Error(`Sonic modelTimeoutException: ${ev.modelTimeoutException.message || "unknown"}`);
          }
          if (ev?.serviceUnavailableException) {
            throw new Error(`Sonic serviceUnavailableException: ${ev.serviceUnavailableException.message || "unknown"}`);
          }
          if (ev?.throttlingException) {
            throw new Error(`Sonic throttlingException: ${ev.throttlingException.message || "unknown"}`);
          }

          if (ev?.chunk?.bytes) {
            let eventPayload = null;
            try {
              const raw = Buffer.from(ev.chunk.bytes).toString("utf-8").trim();
              if (!raw) continue;
              const parsed = JSON.parse(raw);
              eventPayload = parsed?.event || parsed;
            } catch {
              continue;
            }
            if (!eventPayload || typeof eventPayload !== "object") {
              continue;
            }

            if (eventPayload.contentStart && eventPayload.contentStart.contentId) {
              const cs = eventPayload.contentStart;
              const cid = String(cs.contentId);
              contentMetaById.set(cid, {
                role: String(cs.role || ""),
                type: String(cs.type || ""),
                generationStage: String(cs.generationStage || ""),
              });
              if (cs.type === "AUDIO" && cs.audioOutputConfiguration?.sampleRateHertz) {
                const parsedRate = Number(cs.audioOutputConfiguration.sampleRateHertz);
                if (Number.isFinite(parsedRate) && parsedRate > 0) {
                  responseAudioRate = parsedRate;
                }
              }
              if (!textByContentId.has(cid)) {
                textByContentId.set(cid, "");
                contentOrder.push(cid);
              }
            }

            if (eventPayload.textOutput && eventPayload.textOutput.contentId) {
              const to = eventPayload.textOutput;
              const cid = String(to.contentId);
              if (!textByContentId.has(cid)) {
                textByContentId.set(cid, "");
                contentOrder.push(cid);
              }
              textByContentId.set(cid, `${textByContentId.get(cid) || ""}${String(to.content || "")}`);
            }

            if (eventPayload.audioOutput?.content) {
              try {
                audioChunks.push(Buffer.from(String(eventPayload.audioOutput.content), "base64"));
              } catch {
                // Ignore malformed chunk; continue streaming.
              }
            }
          }
        }

        const assistantFinal = [];
        const assistantAny = [];
        for (const cid of contentOrder) {
          const meta = contentMetaById.get(cid);
          const text = String(textByContentId.get(cid) || "");
          if (!text) continue;
          if (meta?.role !== "ASSISTANT") continue;
          assistantAny.push(text);
          if (String(meta.generationStage || "").toUpperCase() === "FINAL") {
            assistantFinal.push(text);
          }
        }
        const transcript = (assistantFinal.length ? assistantFinal : assistantAny).join("").trim();

        const audioPcm16 = Buffer.concat(audioChunks);
        const wav = wavFromPcm16({ pcm16: audioPcm16, sampleRateHertz: responseAudioRate, channelCount: 1 });

        return {
          transcript,
          response_audio_pcm16_base64: audioPcm16.toString("base64"),
          response_audio_wav_base64: wav.toString("base64"),
          model_id_used: modelId,
        };
      } catch (e) {
        lastError = e;
        attemptErrors.push({ modelId, attempt, message: String(e?.message || e) });
        if (attempt < maxAttemptsPerModel && isRetryableSonicError(e)) {
          await sleep(200 * attempt);
          continue;
        }
        break;
      }
    }
  }
  const suffix =
    attemptErrors.length > 0
      ? ` Attempts: ${attemptErrors.map((x) => `${x.modelId}: ${x.message}`).join(" | ")}`
      : "";
  const base = String(lastError?.message || "Sonic invocation failed for all model candidates.");
  throw new Error(`${base}${suffix}`);
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET,POST,OPTIONS",
        "access-control-allow-headers": "content-type",
      });
      res.end();
      return;
    }

    if (req.method === "GET" && req.url === "/health") {
      json(res, 200, {
        ok: true,
        region: REGION,
        model_id_configured: Boolean(MODEL_ID),
        configured_model_id: MODEL_ID || null,
        model_candidates: sonicModelCandidates(),
      });
      return;
    }

    if (req.method === "POST" && req.url === "/v1/voice/sonic") {
      const body = await readJsonBody(req);
      const audioPcm16Base64 = String(body.audioPcm16Base64 || "");
      const sampleRateHertz = Number(body.sampleRateHertz || 16000);
      const userText = String(body.userText || "");
      const systemText = String(body.systemText || "");

      if (!audioPcm16Base64) {
        json(res, 400, { ok: false, error: "Missing audioPcm16Base64 (base64 PCM16LE)" });
        return;
      }

      const out = await sonicRoundTrip({
        audioPcm16Base64,
        sampleRateHertz,
        userText,
        systemText: systemText || undefined,
      });
      json(res, 200, { ok: true, ...out });
      return;
    }

    json(res, 404, { ok: false, error: "not_found" });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e?.message || e), details: errorDetails(e) });
  }
});

server.listen(PORT, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`LeakSentinel voice service listening on :${PORT} (region=${REGION})`);
});
