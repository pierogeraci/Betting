import { Readable } from "node:stream";
import { eq } from "drizzle-orm";
import { Router, type IRouter, type Request, type Response } from "express";
import { RequestUploadUrlBody, RequestUploadUrlResponse } from "@workspace/api-zod";
import { db, ctiEvidenceTable, ctiSourcesTable } from "@workspace/db";
import { isSafeObjectPath } from "../lib/cti-utils";
import { ObjectNotFoundError, ObjectStorageService } from "../lib/objectStorage";

const router: IRouter = Router();
const storage = new ObjectStorageService();
const maxFileBytes = 15 * 1024 * 1024;
const allowedTypes = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
  "text/plain",
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

router.post(
  "/storage/uploads/request-url",
  async (req: Request, res: Response): Promise<void> => {
    const parsed = RequestUploadUrlBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const { name, size, contentType, purpose } = parsed.data;
    if (size > maxFileBytes) {
      res.status(400).json({ error: "Files must be 15 MB or smaller" });
      return;
    }
    if (!allowedTypes.has(contentType.toLowerCase())) {
      res.status(400).json({ error: "This file type is not allowed for the prototype" });
      return;
    }
    try {
      const uploadURL = await storage.getObjectEntityUploadURL();
      const objectPath = storage.normalizeObjectEntityPath(uploadURL);
      const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString();
      res.json(
        RequestUploadUrlResponse.parse({
          uploadURL,
          objectPath,
          expiresAt,
          metadata: { name, size, contentType, purpose },
        }),
      );
    } catch (error) {
      req.log.error({ err: error }, "Could not create private upload URL");
      res.status(500).json({ error: "Could not create upload URL" });
    }
  },
);

router.get(
  "/storage/objects/*path",
  async (req: Request, res: Response): Promise<void> => {
  try {
    const raw = req.params.path;
    const objectPath = `/objects/${Array.isArray(raw) ? raw.join("/") : raw}`;
    if (!isSafeObjectPath(objectPath)) {
      res.status(404).json({ error: "Object not found" });
      return;
    }
    const [evidence] = await db
      .select({ id: ctiEvidenceTable.id })
      .from(ctiEvidenceTable)
      .where(eq(ctiEvidenceTable.attachmentPath, objectPath))
      .limit(1);
    const [source] = await db
      .select({ id: ctiSourcesTable.id })
      .from(ctiSourcesTable)
      .where(eq(ctiSourcesTable.authorizationEvidencePath, objectPath))
      .limit(1);
    if (!evidence && !source) {
      res.status(404).json({ error: "Object not found" });
      return;
    }
    const file = await storage.getObjectEntityFile(objectPath);
    const response = await storage.downloadObject(file, 0);
    res.status(response.status);
    response.headers.forEach((value, key) => res.setHeader(key, value));
    if (response.body) {
      Readable.fromWeb(response.body as ReadableStream<Uint8Array>).pipe(res);
    } else {
      res.end();
    }
  } catch (error) {
    if (error instanceof ObjectNotFoundError) {
      res.status(404).json({ error: "Object not found" });
      return;
    }
    req.log.error({ err: error }, "Could not serve private object");
    res.status(500).json({ error: "Could not serve object" });
  }
  },
);

router.get("/storage/public-objects/*filePath", async (req: Request, res: Response): Promise<void> => {
  try {
    const raw = req.params.filePath;
    const filePath = Array.isArray(raw) ? raw.join("/") : raw;
    const file = await storage.searchPublicObject(filePath);
    if (!file) {
      res.status(404).json({ error: "Public object not found" });
      return;
    }
    const response = await storage.downloadObject(file);
    res.status(response.status);
    response.headers.forEach((value, key) => res.setHeader(key, value));
    if (response.body) {
      Readable.fromWeb(response.body as ReadableStream<Uint8Array>).pipe(res);
    } else {
      res.end();
    }
  } catch (error) {
    req.log.error({ err: error }, "Could not serve public object");
    res.status(500).json({ error: "Could not serve public object" });
  }
});

export default router;
