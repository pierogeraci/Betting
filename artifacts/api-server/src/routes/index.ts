import { Router, type IRouter } from "express";
import healthRouter from "./health";
import authRouter from "./auth";
import { requireAuthenticated } from "../lib/auth";
import workspaceRouter from "./workspace";
import sourcesRouter from "./sources";
import intelligenceRouter from "./intelligence";
import exportsRouter from "./exports";
import storageRouter, { publicObjectsRouter } from "./storage";

const router: IRouter = Router();

router.use(healthRouter);
router.use(publicObjectsRouter);
router.use(authRouter);
router.use(requireAuthenticated);
router.use(storageRouter);
router.use(workspaceRouter);
router.use(sourcesRouter);
router.use(intelligenceRouter);
router.use(exportsRouter);

export default router;
