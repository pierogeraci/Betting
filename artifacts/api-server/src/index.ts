import app from "./app";
import { seedDevelopmentDemoData } from "./lib/demo-seed";
import { seedInitialLocalAdmin } from "./lib/local-auth-seed";
import { getSessionSecret } from "./lib/local-auth-crypto";
import { logger } from "./lib/logger";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

async function startServer() {
  try {
    getSessionSecret();
    const adminCreated = await seedInitialLocalAdmin();
    if (adminCreated) logger.info("Created the configured local CTI administrator");
    const seeded = await seedDevelopmentDemoData();
    if (seeded) logger.info("Loaded synthetic CTI demonstration records");
  } catch (err) {
    logger.error({ err }, "Could not prepare CTI demonstration data");
    process.exit(1);
  }

  app.listen(port, (err) => {
    if (err) {
      logger.error({ err }, "Error listening on port");
      process.exit(1);
    }

    logger.info({ port }, "Server listening");
  });
}

void startServer();
