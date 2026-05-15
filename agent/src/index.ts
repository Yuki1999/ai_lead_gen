import { loadConfig } from "./config.js";
import { runPiChat, runPiChatStream } from "./piSession.js";
import { createServer } from "./server.js";

const config = loadConfig();
const server = createServer({ runChat: runPiChat, runChatStream: runPiChatStream });

server.listen(config.port, config.host, () => {
  console.log(
    `Medbot Pi agent sidecar listening on http://${config.host}:${config.port}`,
  );
});
